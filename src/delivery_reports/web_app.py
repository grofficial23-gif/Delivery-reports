from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from telegram import Bot
from telegram.error import TelegramError

from .config import Settings, load_settings
from .db import Database
from .repository import NewPMTask, Repository, UserProfile
from .services.mini_app_auth import (
    issue_session_token,
    read_session_user_id,
    validate_init_data,
)
from .services.note_capture import (
    render_saved_notes_message,
    store_notes as capture_notes,
)
from .services.draft_revision import parse_revision_instruction
from .services.intent import infer_intent_kind, label_for_kind
from .services.parsing import parse_note_text
from .services.project_resolution import (
    fallback_project_ids,
    project_names_by_ids,
    resolve_lead_name,
    resolve_manager_name,
    resolve_or_create_project,
    resolve_project_for_block,
)
from .services.report_presenter import (
    build_note_preview,
    html_report_to_plain_text,
    split_telegram_chunks,
)
from .services.report_preferences import (
    resolve_style_for_user,
    selected_template_key,
    set_selected_template_key,
)
from .services.reporting import build_and_store_daily_draft, finalize_daily_report
from .shared import task_status_label, today_date


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "web" / "templates"
STATIC_DIR = BASE_DIR / "web" / "static"

SESSION_COOKIE_NAME = "delivery_reports_session"


def build_web_app(settings: Settings, repository: Repository) -> FastAPI:
    app = FastAPI(title="Delivery Reports Mini App")
    app.state.settings = settings
    app.state.repository = repository
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request) -> HTMLResponse:
        # Simple anonymous event if no user context
        repository.log_event(0, "visit_landing", request.client.host if request.client else "")
        template_name = "landing_v2.html" if settings.landing_ui_version == "v2" else "landing.html"
        return templates.TemplateResponse(
            request=request,
            name=template_name,
            context={
                "request": request,
                "bot_username": settings.bot_username,
                "bot_url": f"https://t.me/{settings.bot_username}",
                "public_web_app_url": settings.public_web_app_url,
                "app_version": settings.app_version,
            },
        )

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request) -> HTMLResponse:
        from .services.admin import AdminService
        user = _authenticated_user(request, repository, settings)
        is_admin = False
        is_team_admin = False
        if user:
            from .services.subscription import SubscriptionService
            sub_svc = SubscriptionService(repository.db)
            if sub_svc.get_user_plan(user.telegram_user_id) == "team":
                # Only the team owner sees Team Admin; members without an owned team
                # row are redirected with a friendly notice.
                with repository.db.connect() as _conn:
                    _owns = _conn.execute(
                        "SELECT 1 FROM teams WHERE owner_user_id = ?",
                        (user.telegram_user_id,),
                    ).fetchone()
                if _owns:
                    is_team_admin = True

            if user.telegram_username:
                admin_svc = AdminService(repository.db, settings)
                is_admin = admin_svc.is_super_admin(user.telegram_username)

        if not is_admin and not is_team_admin:
            return RedirectResponse(url="/dashboard?notice=" + quote_plus("Нет доступа к админке"))
            
        admin_svc = AdminService(repository.db, settings)
        stats = admin_svc.get_platform_stats() if is_admin else None
        
        users = []
        events = []
        heatmap = []
        team_name = ""
        
        if is_admin:
            users = admin_svc.list_users(limit=50)
            with repository.db.connect() as conn:
                event_rows = conn.execute(
                    "SELECT e.created_at, e.event_type, e.event_data, u.telegram_username, u.display_name "
                    "FROM analytics_events e "
                    "LEFT JOIN users u ON e.user_id = u.telegram_user_id "
                    "ORDER BY e.created_at DESC LIMIT 50"
                ).fetchall()
                for r in event_rows:
                    events.append(dict(r))
        elif is_team_admin:
            with repository.db.connect() as conn:
                team_row = conn.execute("SELECT id, name FROM teams WHERE owner_user_id = ?", (user.telegram_user_id,)).fetchone()
                if team_row:
                    team_name = team_row["name"]
                    team_id = team_row["id"]
                    
                    member_rows = conn.execute(
                        """
                        SELECT u.telegram_user_id, u.display_name, u.telegram_username, tm.role
                        FROM team_members tm
                        JOIN users u ON tm.user_id = u.telegram_user_id
                        WHERE tm.team_id = ?
                        """, (team_id,)
                    ).fetchall()
                    users = [dict(r) for r in member_rows]
                    
                    # Basic Heatmap data (notes count per user per day for last 7 days)
                    heatmap_rows = conn.execute(
                        """
                        SELECT user_id, note_date, COUNT(id) as count
                        FROM notes
                        WHERE user_id IN (SELECT user_id FROM team_members WHERE team_id = ?)
                          AND date(note_date) >= date('now', '-7 days')
                        GROUP BY user_id, note_date
                        """, (team_id,)
                    ).fetchall()
                    heatmap = [dict(r) for r in heatmap_rows]

        return templates.TemplateResponse(request=request, name="admin.html", context={
            "request": request, 
            "notice": request.query_params.get("notice", ""),
            "stats": stats, 
            "users": users,
            "events": events,
            "heatmap": heatmap,
            "team_name": team_name,
            "is_super_admin": is_admin,
            "user": user,
            "bot_username": settings.bot_username,
            "bot_url": f"https://t.me/{settings.bot_username}",
            "app_version": settings.app_version,
        })

    @app.post("/admin/users/{target_user_id}/plan")
    async def admin_update_user_plan(target_user_id: int, request: Request) -> RedirectResponse:
        from .services.admin import AdminService
        from .services.subscription import Plan

        user = _authenticated_user(request, repository, settings)
        if user is None or not user.telegram_username:
            return _redirect_admin_with_notice("Откройте приложение из Telegram под admin-аккаунтом.")

        admin_svc = AdminService(repository.db, settings)
        if not admin_svc.is_super_admin(user.telegram_username):
            return _redirect_admin_with_notice("Недостаточно прав для управления тарифами.")

        payload = await _parse_payload(request)
        plan = payload.get("plan", "").strip().lower()
        if plan == Plan.PRO:
            admin_svc.grant_pro(target_user_id)
            return _redirect_admin_with_notice(f"Пользователю {target_user_id} выдан PRO.")
        if plan == Plan.TEAM:
            admin_svc.grant_team(target_user_id)
            return _redirect_admin_with_notice(f"Пользователю {target_user_id} выдан TEAM.")
        if plan == Plan.FREE:
            admin_svc.revoke_subscription(target_user_id)
            return _redirect_admin_with_notice(f"Пользователь {target_user_id} переведен на FREE.")
        return _redirect_admin_with_notice("Неизвестный тариф.")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        context = _build_dashboard_context(request, repository, settings)
        template_name = "dashboard_v2.html" if settings.dashboard_ui_version == "v2" else "index.html"
        return templates.TemplateResponse(request=request, name=template_name, context=context)

    @app.post("/auth/telegram")
    async def auth_telegram(request: Request) -> JSONResponse:
        payload = await _parse_payload(request)
        init_data = payload.get("init_data", "").strip()
        try:
            mini_user = validate_init_data(init_data, settings.telegram_bot_token)
        except ValueError as error:
            return JSONResponse({"ok": False, "error": str(error)}, status_code=400)
        user = _sync_mini_app_user(repository, settings, mini_user.telegram_user_id, mini_user.username, mini_user.full_name)
        response = JSONResponse({"ok": True, "user_id": user.telegram_user_id, "display_name": user.display_name})
        _set_session_cookie(response, settings, user.telegram_user_id)
        return response

    @app.post("/onboarding/complete")
    async def complete_onboarding(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        repository.set_state(_onboarding_key(user.telegram_user_id), "1")
        return _redirect_with_notice("Подсказки скрыты. Их можно открыть снова позже.")

    @app.post("/notes")
    async def add_note(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        _ensure_project_from_payload(repository, settings, user, payload)
        raw_text = _compose_note_text(payload)
        if not raw_text:
            return _redirect_with_notice("Заполните хотя бы один блок апдейта.")
        repository.log_event(user.telegram_user_id, "web_add_note", "source=mini_app")
        results, unresolved_note_ids = capture_notes(
            repository=repository,
            settings=settings,
            raw_text=raw_text,
            note_date=_today(settings).isoformat(),
            source="mini_app_text",
            user=user,
            transcript_text="",
        )
        notice = render_saved_notes_message(results)
        if unresolved_note_ids:
            notice += f"\nНужно уточнить: {len(unresolved_note_ids)}."
        if payload.get("action", "").strip() == "save_build":
            style = resolve_style_for_user(repository, user.telegram_user_id)
            build_and_store_daily_draft(
                repository,
                settings,
                _today(settings),
                user_id=user.telegram_user_id,
                style=style,
            )
            notice += "\nЧерновик обновлен."
        notice += f"\n\n{_day_progress_message(repository, settings, user)}"
        return _redirect_with_notice(notice)

    @app.post("/tasks")
    async def add_task(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        title = payload.get("title", "").strip()
        if not title:
            return _redirect_with_notice("Добавьте текст задачи.")
        task_id = _add_task(repository, settings, user, title)
        return _redirect_with_notice(f"Задача #{task_id} добавлена.")

    @app.post("/tasks/{task_id}/status")
    async def update_task_status(task_id: int, request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        next_status = payload.get("status", "").strip().lower()
        if not repository.update_task_status(task_id, user.telegram_user_id, next_status):
            return _redirect_with_notice("Не удалось обновить статус задачи.")
        return _redirect_with_notice(f"Статус задачи #{task_id} обновлен.")

    @app.post("/draft/build")
    async def build_draft(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        repository.log_event(user.telegram_user_id, "web_build_draft")
        style = resolve_style_for_user(repository, user.telegram_user_id)
        build_and_store_daily_draft(
            repository,
            settings,
            _today(settings),
            user_id=user.telegram_user_id,
            style=style,
        )
        return _redirect_with_notice("Черновик собран.")

    @app.post("/draft/revise")
    async def revise_draft(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")

        payload = await _parse_payload(request)
        instruction = payload.get("instruction", "").strip().lower()
        instruction_map = {
            "concise": "сделать короче",
            "executive": "командный",
            "risk_focus": "акцент на риск",
        }
        mapped_instruction = instruction_map.get(instruction, "")
        revision = parse_revision_instruction(mapped_instruction)
        if revision is None:
            return _redirect_with_notice("Неизвестная команда правки")

        target_date = _today(settings)
        draft = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id)
        if not draft:
            return _redirect_with_notice("Сначала соберите черновик")

        build_and_store_daily_draft(
            repository,
            settings,
            target_date,
            user_id=user.telegram_user_id,
            style=revision.style,
        )
        return _redirect_with_notice("Черновик обновлён")

    @app.post("/draft/finalize")
    async def finalize_draft(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        target_date = _today(settings)
        style = resolve_style_for_user(repository, user.telegram_user_id)
        draft = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id)
        if not draft:
            draft = build_and_store_daily_draft(
                repository,
                settings,
                target_date,
                user_id=user.telegram_user_id,
                style=style,
            )
        finalize_daily_report(
            repository,
            target_date,
            draft,
            user.telegram_user_id,
            style=style,
            language="ru",
            bot_username=settings.bot_username,
        )
        return _redirect_with_notice("Финальный отчет зафиксирован.")

    @app.post("/draft/send")
    async def send_draft_to_telegram(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        target_date = _today(settings)
        style = resolve_style_for_user(repository, user.telegram_user_id)
        draft = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id)
        if not draft:
            draft = build_and_store_daily_draft(
                repository,
                settings,
                target_date,
                user_id=user.telegram_user_id,
                style=style,
            )
        try:
            await _send_report_to_telegram(settings, user, draft)
        except RuntimeError as error:
            return _redirect_with_notice(str(error))
        except TelegramError as error:
            return _redirect_with_notice(f"Не удалось отправить черновик в Telegram: {error}")
        return _redirect_with_notice("Черновик отправлен в Telegram.")

    @app.post("/final/send")
    async def send_final_to_telegram(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        final_report = repository.get_latest_final_report_for_date(
            _today(settings),
            author_user_id=user.telegram_user_id,
        )
        if not final_report:
            return _redirect_with_notice("Сначала зафиксируйте финальный отчет.")
        try:
            await _send_report_to_telegram(settings, user, final_report)
        except RuntimeError as error:
            return _redirect_with_notice(str(error))
        except TelegramError as error:
            return _redirect_with_notice(f"Не удалось отправить финальный отчет в Telegram: {error}")
        return _redirect_with_notice("Финальный отчет отправлен в Telegram.")

    @app.post("/inbox/{note_id}/resolve")
    async def resolve_inbox(note_id: int, request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        project_name = payload.get("project_name", "").strip()
        if not project_name:
            return _redirect_with_notice("Укажите проект для inbox-заметки.")
        note = repository.get_note(note_id)
        if note is None or note.user_id != user.telegram_user_id:
            return _redirect_with_notice("Не нашел такую inbox-заметку.")
        project, _created = resolve_or_create_project(project_name, repository, user, settings)
        repository.update_note_project(
            note_id,
            project,
            resolve_manager_name(project, user, settings),
            resolve_lead_name(project, user, settings),
        )
        notice = quote_plus(f"Заметка note#{note_id} привязана к проекту {project.name}.")
        return RedirectResponse(url=f"/dashboard?notice={notice}#inbox", status_code=303)

    @app.post("/inbox/bulk-resolve")
    async def bulk_resolve_inbox(request: Request) -> RedirectResponse:
        # Step 32 — bind multiple inbox notes to one project in one action.
        # Read body once; parse both the multi-value note_ids and project_name.
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        body_bytes = await request.body()
        body_str = body_bytes.decode("utf-8")
        multi = parse_qs(body_str, keep_blank_values=False)
        project_name = (multi.get("project_name", [""])[-1] or "").strip()
        if not project_name:
            return _redirect_with_notice("Укажите проект для привязки.")
        # note_ids may arrive as repeated form fields OR comma/semicolon-separated.
        all_ids_raw = multi.get("note_ids", [])
        id_parts: list[str] = []
        for val in all_ids_raw:
            id_parts.extend(p.strip() for p in val.replace(";", ",").split(",") if p.strip())
        note_ids: list[int] = []
        for part in id_parts:
            try:
                note_ids.append(int(part))
            except ValueError:
                pass
        if not note_ids:
            return _redirect_with_notice("Выберите хотя бы одну заметку.")
        project, _created = resolve_or_create_project(project_name, repository, user, settings)
        bound_count = 0
        for note_id in note_ids:
            note = repository.get_note(note_id)
            if note is None or note.user_id != user.telegram_user_id:
                continue
            repository.update_note_project(
                note_id,
                project,
                resolve_manager_name(project, user, settings),
                resolve_lead_name(project, user, settings),
            )
            bound_count += 1
        if bound_count == 0:
            return _redirect_with_notice("Не удалось привязать выбранные заметки.")
        notice = quote_plus(f"Привязано {bound_count} заметок к проекту {project.name}.")
        return RedirectResponse(url=f"/dashboard?notice={notice}#inbox", status_code=303)

    @app.post("/projects")
    async def create_project(request: Request) -> RedirectResponse:
        # Step 31 — minimal "create project from dashboard" route.
        # Reuses resolve_or_create_project (already exposed for /notes
        # and /inbox/{id}/resolve), then upgrades aliases if user passed any.
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        name = payload.get("project_name", "").strip()
        if not name:
            return _redirect_with_notice("Введите название проекта.")
        project, created = resolve_or_create_project(name, repository, user, settings)
        aliases_raw = payload.get("aliases", "").strip()
        if aliases_raw:
            new_aliases = [a.strip() for a in aliases_raw.replace(";", ",").split(",") if a.strip()]
            if new_aliases:
                merged = sorted({*(project.aliases or []), project.name, *new_aliases})
                project = repository.upsert_project(
                    name=project.name,
                    manager_name=project.manager_name,
                    lead_name=project.lead_name,
                    jira_base_url=project.jira_base_url,
                    aliases=merged,
                    is_special_control=project.is_special_control,
                    owner_user_id=user.telegram_user_id,
                )
        verb = "создан" if created else "обновлён"
        notice = quote_plus(f"Проект «{project.name}» {verb}.")
        return RedirectResponse(url=f"/dashboard?notice={notice}#add-note", status_code=303)

    @app.post("/template")
    async def choose_template(request: Request) -> RedirectResponse:
        user = _authenticated_user(request, repository, settings)
        if user is None:
            return _redirect_with_notice("Откройте приложение из Telegram.")
        payload = await _parse_payload(request)
        template_key = payload.get("template_key", "").strip().lower()
        template = repository.get_report_template(template_key)
        if template is None or not template.is_active:
            return _redirect_with_notice("Не нашел такой шаблон.")
        set_selected_template_key(repository, user.telegram_user_id, template_key)
        return _redirect_with_notice(f"Выбран шаблон: {template.title}.")

    return app


def create_default_web_app() -> FastAPI:
    settings = load_settings()
    repository = Repository(Database(settings.db_path))
    repository.ensure_default_project(settings.default_manager_name, settings.default_lead_name)
    repository.ensure_default_report_templates()
    return build_web_app(settings, repository)


def _build_dashboard_context(request: Request, repository: Repository, settings: Settings) -> dict[str, Any]:
    target_date = _today(settings)
    user = _authenticated_user(request, repository, settings)
    base_context = {
        "request": request,
        "today": target_date.strftime("%d.%m.%Y"),
        "today_iso": target_date.isoformat(),
        "report_date_label": target_date.strftime("%d.%m.%Y"),
        "notice": request.query_params.get("notice", ""),
        "public_web_app_url": settings.public_web_app_url,
        "bot_username": settings.bot_username,
        "bot_url": f"https://t.me/{settings.bot_username}",
        "status_label": task_status_label,
        "app_version": settings.app_version,
    }
    if user is None:
        return {
            **base_context,
            "auth_required": True,
            "is_super_admin": False,
            "is_team_owner": False,
            "user": None,
            "summary": {
                "notes_count": 0,
                "project_count": 0,
                "inbox_count": 0,
                "tasks_count": 0,
                "has_draft": False,
                "has_final": False,
                "draft_chunks": 0,
                "final_chunks": 0,
            },
            "next_action": {
                "kind": "auth",
                "title": "Откройте Mini App из Telegram",
                "description": "Авторизуйтесь через Telegram, чтобы увидеть дашборд.",
                "primary_label": "",
                "target": "",
            },
            "notes": [],
            "recent_updates": [],  # V1 (index.html) still reads this — V2 ignores.
            "inbox_cards": [],
            "tasks": [],
            "projects": [],
            "inbox_projects": [],
            "draft": None,
            "draft_plain": "",
            "final_report": None,
            "final_plain": "",
            "recent_report_history": [],
            "templates": repository.list_report_templates(active_only=True),
            "current_template_key": "team",
            "show_onboarding": False,
            "status_suggestions": _default_status_suggestions(),
            "epic_suggestions": [],
        }

    notes = repository.list_notes_for_user_on_date(user.telegram_user_id, target_date)
    notes.reverse()
    unresolved = repository.list_unresolved_notes_for_user(user.telegram_user_id, target_date=target_date, limit=30)
    tasks = repository.list_tasks_for_user(
        user.telegram_user_id,
        statuses=["open", "in_progress", "waiting"],
        limit=50,
    )
    templates = repository.list_report_templates(active_only=True)
    projects = [
        project
        for project in repository.list_projects(owner_user_id=user.telegram_user_id)
        if project.name.lower() != "без проекта"
    ]
    # Step 28A — separate, robust list for the inbox-binding dropdown. The
    # user-scoped list above can be empty if existing projects in SQLite
    # were created under a different owner_user_id (legacy data, seeder
    # run with a different Telegram id, etc.). The dropdown should still
    # let the user pick a known project; /inbox/{id}/resolve will reconcile
    # ownership via resolve_or_create_project.
    inbox_projects: list = list(projects)
    if not inbox_projects:
        _seen_inbox_names: set[str] = set()
        for project in repository.list_projects(owner_user_id=None):
            norm = project.name.strip().lower()
            if not norm or norm == "без проекта" or norm in _seen_inbox_names:
                continue
            _seen_inbox_names.add(norm)
            inbox_projects.append(project)
    draft = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id)
    final_report = repository.get_latest_final_report_for_date(target_date, author_user_id=user.telegram_user_id)

    inbox_cards = []
    fallback_ids = fallback_project_ids(repository, owner_user_id=user.telegram_user_id)
    for note in unresolved:
        parsed = parse_note_text(note.raw_text, projects)
        resolution = resolve_project_for_block(
            repository=repository,
            block_text=note.raw_text,
            parsed_note=parsed,
            fallback_project_ids=fallback_ids,
            owner_user_id=user.telegram_user_id,
        )
        card = _build_note_card(note, repository, user.telegram_user_id)
        card["candidates"] = project_names_by_ids(
            repository,
            resolution.candidate_project_ids,
            owner_user_id=user.telegram_user_id,
        )[:4]
        inbox_cards.append(card)

    note_cards = [_build_note_card(note, repository, user.telegram_user_id) for note in notes[:20]]

    current_template_key = selected_template_key(repository, user.telegram_user_id)
    if not current_template_key:
        default_template = repository.get_default_report_template()
        current_template_key = default_template.template_key if default_template else "standard"

    draft_plain = html_report_to_plain_text(draft or "")
    final_plain = html_report_to_plain_text(final_report or "")
    draft_chunks = split_telegram_chunks(draft_plain)
    final_chunks = split_telegram_chunks(final_plain)
    history_items: list[dict[str, str]] = []
    for draft_row in repository.list_recent_drafts(user.telegram_user_id, limit=7):
        draft_snippet = html_report_to_plain_text(draft_row.get("content", ""))
        history_items.append(
            {
                "date": draft_row.get("draft_date", ""),
                "type": "draft",
                "snippet": draft_snippet[:180],
                "created_at": draft_row.get("created_at", ""),
            }
        )
    for final_row in repository.list_recent_final_reports(user.telegram_user_id, limit=7):
        final_snippet = html_report_to_plain_text(final_row.get("content", ""))
        history_items.append(
            {
                "date": final_row.get("report_date", ""),
                "type": "final",
                "snippet": final_snippet[:180],
                "created_at": final_row.get("created_at", ""),
            }
        )
    history_items.sort(
        key=lambda item: ((item.get("created_at") or ""), (item.get("date") or "")),
        reverse=True,
    )
    recent_report_history = history_items[:10]
    summary = {
        "notes_count": len(notes),
        "project_count": _project_count_for_notes(notes, repository, user.telegram_user_id),
        "inbox_count": len(unresolved),
        "tasks_count": len(tasks),
        "has_draft": bool(draft),
        "has_final": bool(final_report),
        "draft_chunks": len(draft_chunks),
        "final_chunks": len(final_chunks),
        "activity_count": len(notes),
    }
    is_super_admin = False
    user_plan = "free"
    days_left = None
    if user:
        from .services.subscription import SubscriptionService
        sub_svc = SubscriptionService(repository.db)
        user_plan = sub_svc.get_user_plan(user.telegram_user_id)
        days_left = sub_svc.get_days_left(user.telegram_user_id)
        
        if user.telegram_username:
            from .services.admin import AdminService
            is_super_admin = AdminService(repository.db, settings).is_super_admin(user.telegram_username)

    # True only when the authenticated user is the owner of a team row.
    # Non-owner TEAM members have user_plan=="team" but no teams.owner_user_id row.
    is_team_owner = False
    if user and user_plan == "team" and not is_super_admin:
        with repository.db.connect() as conn:
            owns = conn.execute(
                "SELECT 1 FROM teams WHERE owner_user_id = ?",
                (user.telegram_user_id,),
            ).fetchone()
        if owns:
            is_team_owner = True

    # Determine the single most important next action for the user.
    if summary["notes_count"] == 0:
        next_action = {
            "kind": "add_note",
            "title": "Добавьте первую заметку",
            "description": (
                "Отправьте текст или голосовое сообщение боту — "
                "или напишите заметку прямо здесь."
            ),
            "primary_label": "Добавить заметку",
            "target": "#add-note",
        }
    elif summary["inbox_count"] > 0 and not draft_plain:
        next_action = {
            "kind": "triage_inbox",
            "title": f"Разберите {summary['inbox_count']} заметок без проекта",
            "description": "Без проекта заметки не попадут в нужный блок отчёта.",
            "primary_label": "Разобрать",
            "target": "#inbox",
            "count": summary["inbox_count"],
        }
    elif summary["notes_count"] > 0 and not draft_plain:
        next_action = {
            "kind": "build_draft",
            "title": "Соберите черновик",
            "description": f"Есть {summary['notes_count']} заметок — соберите черновик отчёта.",
            "primary_label": "Собрать черновик",
            "target": "#draft",
        }
    elif draft_plain and not final_report:
        next_action = {
            "kind": "review_draft",
            "title": "Проверьте и отправьте черновик",
            "description": "Черновик готов. Отправьте себе в Telegram для проверки.",
            "primary_label": "Отправить в Telegram",
            "target": "#draft",
        }
    elif final_report:
        next_action = {
            "kind": "done_today",
            "title": "Готово на сегодня",
            "description": "Финальный отчёт зафиксирован. Можно отправить ещё раз.",
            "primary_label": "Отправить финал ещё раз",
            "target": "#draft",
        }
    else:
        next_action = {
            "kind": "build_draft",
            "title": "Соберите черновик",
            "description": "Нажмите, чтобы собрать черновик из заметок.",
            "primary_label": "Собрать черновик",
            "target": "#draft",
        }

    return {
        **base_context,
        "auth_required": False,
        "user": user,
        "is_super_admin": is_super_admin,
        "is_team_owner": is_team_owner,
        "user_plan": user_plan,
        "days_left": days_left,
        "summary": summary,
        "next_action": next_action,
        "notes": note_cards,
        "recent_updates": note_cards[:6],  # V1 (index.html) still reads this — V2 ignores.
        "inbox_cards": inbox_cards,
        "tasks": tasks,
        "projects": projects,
        "inbox_projects": inbox_projects,
        "draft": draft,
        "draft_plain": draft_plain,
        "final_report": final_report,
        "final_plain": final_plain,
        "recent_report_history": recent_report_history,
        "templates": templates,
        "current_template_key": current_template_key,
        "show_onboarding": repository.get_state(_onboarding_key(user.telegram_user_id)) != "1",
        "status_suggestions": _status_suggestions(notes),
        "epic_suggestions": _epic_suggestions(repository, notes, user.telegram_user_id),
    }


async def _parse_payload(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
        return {str(key): str(value) for key, value in payload.items() if value is not None}
    body = (await request.body()).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _redirect_with_notice(text: str) -> RedirectResponse:
    return RedirectResponse(url=f"/dashboard?notice={quote_plus(text)}", status_code=303)


def _redirect_admin_with_notice(text: str) -> RedirectResponse:
    return RedirectResponse(url=f"/admin?notice={quote_plus(text)}", status_code=303)


def _authenticated_user(request: Request, repository: Repository, settings: Settings) -> UserProfile | None:
    user_id = read_session_user_id(
        request.cookies.get(SESSION_COOKIE_NAME, ""),
        settings.web_session_secret,
    )
    if user_id is None:
        return None
    return repository.get_user(user_id)


def _set_session_cookie(response: JSONResponse | RedirectResponse, settings: Settings, user_id: int) -> None:
    token = issue_session_token(user_id, settings.web_session_secret)
    is_https = settings.public_web_app_url.startswith("https://")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=is_https,
        samesite="none" if is_https else "lax",
        path="/",
    )


def _sync_mini_app_user(
    repository: Repository,
    settings: Settings,
    telegram_user_id: int,
    telegram_username: str,
    telegram_full_name: str,
) -> UserProfile:
    profile = repository.upsert_user(
        telegram_user_id=telegram_user_id,
        telegram_username=telegram_username,
        telegram_full_name=telegram_full_name,
    )
    display_name = profile.display_name or profile.telegram_full_name
    manager_name = profile.default_manager_name or display_name
    lead_name = profile.default_lead_name or settings.default_lead_name
    profile = repository.update_user_defaults(
        profile.telegram_user_id,
        display_name=display_name,
        default_manager_name=manager_name,
        default_lead_name=lead_name,
    )
    repository.ensure_default_project(manager_name, lead_name, owner_user_id=profile.telegram_user_id)
    return profile


def _add_task(repository: Repository, settings: Settings, user: UserProfile, title: str) -> int:
    projects = repository.list_projects(owner_user_id=user.telegram_user_id)
    parsed = parse_note_text(title, projects)
    resolution = resolve_project_for_block(
        repository=repository,
        block_text=title,
        parsed_note=parsed,
        fallback_project_ids=fallback_project_ids(repository, owner_user_id=user.telegram_user_id),
        owner_user_id=user.telegram_user_id,
    )
    jira_key = ""
    for link in parsed.jira_links:
        tail = link.rsplit("/", 1)[-1]
        if "-" in tail:
            jira_key = tail.upper()
            break
    task = NewPMTask(
        owner_user_id=user.telegram_user_id,
        title=title,
        project_id=resolution.project_id,
        epic=parsed.epic,
        jira_key=jira_key,
        jira_url=parsed.jira_links[0] if parsed.jira_links else "",
        status="open",
        source="mini_app",
    )
    return repository.add_task(task)


def _ensure_project_from_payload(
    repository: Repository,
    settings: Settings,
    user: UserProfile,
    payload: dict[str, str],
) -> None:
    project_name = payload.get("project_name", "").strip()
    raw_text = payload.get("text", "").strip()
    if raw_text or not project_name:
        return
    resolve_or_create_project(project_name, repository, user, settings)


def _compose_note_text(payload: dict[str, str]) -> str:
    raw_text = payload.get("text", "").strip()
    if raw_text:
        return raw_text

    project_name = payload.get("project_name", "").strip()
    epic_name = payload.get("epic_name", "").strip()
    status_text = payload.get("status_text", "").strip()
    done_text = payload.get("done_text", "").strip()
    plan_text = payload.get("plan_text", "").strip()
    risk_text = payload.get("risk_text", "").strip()
    links_text = payload.get("links_text", "").strip()

    lines: list[str] = []
    if project_name:
        lines.append(f"Проект: {project_name}")
    if epic_name:
        lines.append(f"Эпик: {epic_name}")
    if status_text:
        lines.append(f"Статус: {status_text}")
    if done_text:
        lines.append("Что сделано:")
        lines.extend(_as_bullets(done_text))
    if plan_text:
        lines.append("План на завтра:")
        lines.extend(_as_bullets(plan_text))
    if risk_text:
        lines.append("Риски:")
        lines.extend(_as_bullets(risk_text))
    if links_text:
        lines.append("Ссылки:")
        lines.extend(_as_bullets(links_text))
    return "\n".join(lines).strip()


def _as_bullets(text: str) -> list[str]:
    lines = [line.strip("-• \t") for line in text.splitlines()]
    return [f"- {line}" for line in lines if line]


def _build_note_card(note, repository: Repository, owner_user_id: int) -> dict[str, Any]:
    project = repository.get_project(note.project_id, owner_user_id=owner_user_id) if note.project_id else None
    project_name = project.name if project is not None else "Без проекта"
    intent_kind = infer_intent_kind(
        done_text=note.done_text,
        plan_text=note.plan_text,
        risk_text=note.risk_text,
        needs_review=bool(note.needs_review),
    )
    return {
        "note": note,
        "preview_text": build_note_preview(note),
        "project_name": project_name,
        "has_project": project is not None,
        "epic_name": note.epic.strip(),
        "link_count": len(note.jira_links),
        "links": note.jira_links,
        "intent_kind": intent_kind,
        "intent_label": label_for_kind(intent_kind),
    }


def _project_count_for_notes(notes: list, repository: Repository, owner_user_id: int) -> int:
    labels = {_note_group_label(note, repository, owner_user_id) for note in notes}
    labels.discard("Без проекта")
    return len(labels)


def _note_group_label(note, repository: Repository, owner_user_id: int) -> str:
    if note.project_id:
        project = repository.get_project(note.project_id, owner_user_id=owner_user_id)
        if project is not None:
            return project.name
    if note.epic.strip():
        return note.epic.strip()
    return "Без проекта"


def _status_suggestions(notes: list) -> list[str]:
    suggestions = _default_status_suggestions()
    seen = {value.lower() for value in suggestions}
    for note in notes:
        status_text = note.status_text.strip()
        if not status_text:
            continue
        lowered = status_text.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        suggestions.append(status_text)
    return suggestions[:10]


def _default_status_suggestions() -> list[str]:
    return ["в работе", "тесты", "ждем ответ", "готово", "на согласовании"]


def _epic_suggestions(repository: Repository, notes: list, owner_user_id: int) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for epic in repository.list_epics(owner_user_id=owner_user_id):
        key = epic.name.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        values.append(epic.name.strip())
    for note in notes:
        epic_name = note.epic.strip()
        key = epic_name.lower()
        if not epic_name or key in seen:
            continue
        seen.add(key)
        values.append(epic_name)
    return values[:20]


def _day_progress_message(repository: Repository, settings: Settings, user: UserProfile) -> str:
    notes = repository.list_notes_for_user_on_date(user.telegram_user_id, _today(settings))
    projects_count = _project_count_for_notes(notes, repository, user.telegram_user_id)
    return (
        f"Сегодня уже добавлено: <b>{len(notes)}</b> апдейт(ов) "
        f"по <b>{projects_count}</b> проект(ам). "
        "Можно сразу добавить следующий или собрать digest."
    )


async def _send_report_to_telegram(settings: Settings, user: UserProfile, text: str) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("Не настроен TELEGRAM_BOT_TOKEN. Сначала заполните .env.")
    plain_text = html_report_to_plain_text(text)
    chunks = split_telegram_chunks(plain_text)
    if not chunks:
        raise RuntimeError("Не удалось подготовить текст для отправки.")
    async with Bot(token=settings.telegram_bot_token) as bot:
        for chunk in chunks:
            await bot.send_message(chat_id=user.telegram_user_id, text=chunk)

def _today(settings: Settings):
    return today_date(settings)


def _onboarding_key(user_id: int) -> str:
    return f"mini_onboarding:{user_id}"


# task_status_label is imported from shared.py
_web_status_label = task_status_label
