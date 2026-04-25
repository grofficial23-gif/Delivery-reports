from __future__ import annotations

from datetime import datetime, time as dtime
from html import escape
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MenuButtonWebApp,
    ReplyKeyboardMarkup,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import Settings
from .repository import NewPMTask, Project, Repository, UserProfile
from .services.draft_builder import build_daily_draft
from .services.draft_revision import parse_revision_instruction, revision_help_text
from .services.note_capture import (
    StoredNoteResult,
    render_saved_notes_message as render_captured_notes_message,
    store_notes as capture_notes,
)
from .services.parsing import parse_note_text
from .services.project_resolution import (
    fallback_project_ids,
    looks_like_project_name,
    parse_epic_definition,
    parse_project_definition,
    project_names_by_ids,
    resolve_lead_name,
    resolve_manager_name,
    resolve_or_create_project,
    resolve_project_for_block,
)
from .shared import JIRA_KEY_RE as TASK_JIRA_KEY_RE, task_status_label, today_date
from .services.report_preferences import (
    default_template_style,
    resolve_style_for_user,
    selected_template_key,
    set_selected_template_key,
)
from .services.reporting import build_and_store_daily_draft, finalize_daily_report
from .services.admin import AdminService
from .services.smart_input import SmartInputAction, parse_smart_input
from .services.subscription import Plan, SubscriptionService
from .services.transcription import TranscriptionService


BTN_BUILD_DRAFT = "📋 Собрать отчёт"
BTN_SHOW_DRAFT = "Показать черновик"
BTN_EDIT_DRAFT = "Исправить черновик"
BTN_ADD_NOTE = "Добавить заметку"
BTN_FINALIZE = "Зафиксировать финальный"
BTN_SHOW_FINAL = "Показать финальный"
BTN_MY_TASKS = "✅ Мои задачи"
BTN_INBOX = "Inbox"
BTN_STATUS = "📊 Статус"
BTN_PRO = "⭐ PRO"
BTN_SKIP = "Пропустить"
CORRECTION_RE = re.compile(r"^\s*не\s+(.+?)\s*,?\s+а\s+(.+?)\s*$", re.IGNORECASE)


def build_app(settings: Settings, repository: Repository, transcription: TranscriptionService) -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required in .env")

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data["settings"] = settings
    app.bot_data["repository"] = repository
    app.bot_data["transcription"] = transcription

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("app", cmd_open_app))
    app.add_handler(CommandHandler("pro", cmd_pro))
    app.add_handler(CommandHandler("add", cmd_add))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("draft", cmd_draft))
    app.add_handler(CommandHandler("showdraft", cmd_show_draft))
    app.add_handler(CommandHandler("fixdraft", cmd_fix_draft))
    app.add_handler(CommandHandler("finalize", cmd_finalize))
    app.add_handler(CommandHandler("final", cmd_show_final))
    app.add_handler(CommandHandler("reprocess", cmd_reprocess))
    app.add_handler(CommandHandler("templates", cmd_templates))
    app.add_handler(CommandHandler("template", cmd_template))
    app.add_handler(CommandHandler("task", cmd_task))
    app.add_handler(CommandHandler("mytasks", cmd_mytasks))
    app.add_handler(CommandHandler("inbox", cmd_inbox))
    app.add_handler(CommandHandler("projects", cmd_projects))
    app.add_handler(CommandHandler("epics", cmd_epics))
    # Super Admin commands — only for SUPER_ADMIN_USERNAMES
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("adminuser", cmd_admin_user))
    app.add_handler(CommandHandler("grantpro", cmd_grant_pro))
    app.add_handler(CommandHandler("grantteam", cmd_grant_team))
    app.add_handler(CommandHandler("revokeplan", cmd_revoke_plan))
    app.add_handler(MessageHandler(filters.VOICE, on_voice_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text_message))

    schedule_daily_draft(app, settings)
    return app


def schedule_daily_draft(app: Application, settings: Settings) -> None:
    if app.job_queue is None:
        return
    trigger_time = dtime(
        hour=settings.daily_draft_hour,
        minute=settings.daily_draft_minute,
        tzinfo=ZoneInfo(settings.timezone),
    )
    app.job_queue.run_daily(send_daily_draft_job, time=trigger_time, name="daily-draft")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.effective_user or not update.message:
        return
    repository = _repo(context)
    user = _sync_user_profile(update, context)
    text = (
        "<b>PM Digest Bot готов</b>\n\n"
        f"<b>Автор:</b> {escape(user.default_manager_name or user.display_name or user.telegram_full_name or '-')}\n"
        f"<b>Руководитель:</b> {escape(user.default_lead_name or '-')}\n\n"
        "<b>Как проще всего работать</b>\n"
        "1. Откройте Mini App через menu button или команду <code>/app</code>.\n"
        "2. Один апдейт = один проект, эпик или отдельный смысловой блок.\n"
        "3. В течение дня добавляйте апдейты, а когда будете готовы, нажмите <b>📋 Собрать отчёт</b>.\n"
        "4. Кнопка <b>📊 Статус</b> показывает, что уже собрано за день."
    )
    await _reply_html(update.message, text, reply_markup=_base_keyboard())
    await _maybe_send_mini_app_entry(update, context, user)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    text = (
        "<b>Минимальная инструкция</b>\n"
        "1. Основной интерфейс: <code>/app</code> или menu button <b>Mini App</b>.\n"
        "2. Один апдейт = один проект или эпик.\n"
        "3. После сохранения апдейт попадает в список за день.\n"
        "4. Когда готовы, нажмите <b>📋 Собрать отчёт</b>.\n\n"
        "<b>Кнопки внизу</b>\n"
        f"- <b>{escape(BTN_BUILD_DRAFT)}</b> — собрать digest из текущих апдейтов.\n"
        f"- <b>{escape(BTN_STATUS)}</b> — показать, что уже собрано за сегодня.\n"
        f"- <b>{escape(BTN_MY_TASKS)}</b> — follow-up список.\n"
        f"- <b>{escape(BTN_PRO)}</b> — тарифы и Premium-возможности.\n\n"
        "<b>Быстрые примеры</b>\n"
        "<code>задача: согласовать окно ночных работ</code>\n"
        "<code>готово 12</code>\n"
        "<code>жду 7</code>\n"
        "<code>разобрать 15 DC701</code>\n"
        "<code>короче</code>\n\n"
        "<b>Расширенные команды</b>\n"
        "<code>/app</code>, <code>/status</code>, <code>/draft</code>, <code>/fixdraft</code>, "
        "<code>/finalize</code>, <code>/final</code>, <code>/task</code>, <code>/mytasks</code>, "
        "<code>/inbox</code>, <code>/pro</code>"
    )
    await _reply_html(update.message, text, reply_markup=_base_keyboard())


async def cmd_pro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    subscription = SubscriptionService(_repo(context).db)
    current_plan = subscription.get_user_plan(user.telegram_user_id)
    current_plan_label = subscription.plan_display_name(current_plan)
    lines = [
        "<b>PM Digest Pro</b>",
        "",
        f"<b>Ваш текущий план:</b> {escape(current_plan_label)}",
        "",
        "<b>FREE</b>",
        "- до 3 проектов",
        "- до 10 заметок в день",
        "- базовый стиль отчета",
        "",
        "<b>PRO · $2.49 / мес</b>",
        "- безлимитные проекты и заметки",
        "- rich-форматы и несколько стилей",
        "- weekly-отчеты, экспорт, AI-правки",
        "",
        "<b>TEAM · $6.99 / мес</b>",
        "- командные шаблоны и расширенная история",
        "- monthly / презентации / документация",
        "- админка и аналитика для команды",
        "",
        "<i>Telegram Stars и оплата будут следующим этапом. Пока это продуктовый preview тарификации.</i>",
    ]
    if current_plan == Plan.FREE:
        lines.insert(4, "<b>Что дает апгрейд</b>")
        lines.insert(5, "- больше шаблонов, rich-format, weekly-отчеты и AI-правки")
        lines.insert(6, "")
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def cmd_open_app(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user or not update.effective_chat:
        return
    user = _sync_user_profile(update, context)
    await _maybe_send_mini_app_entry(update, context, user, force_message=True)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    user = _sync_user_profile(update, context)
    raw_text = " ".join(context.args).strip()
    if not raw_text:
        await update.message.reply_text("Добавьте текст после /add, например: /add Сделали тесты по Онбордингу.")
        return
    results = _store_notes(raw_text, source="manual_text", context=context, user=user)
    await update.message.reply_text(
        render_captured_notes_message(results),
        reply_markup=_reply_markup_for_results(results),
        parse_mode=ParseMode.HTML,
    )


async def cmd_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    style = resolve_style_for_user(_repo(context), user.telegram_user_id)
    content = _build_and_store_today_draft_with_style(context, user, style=style)
    await update.message.reply_text(content, reply_markup=_base_keyboard(), parse_mode=ParseMode.HTML)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    await update.message.reply_text(
        _build_status_message(context, user),
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_show_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    draft = _repo(context).get_latest_draft_for_date(_today(context), owner_user_id=user.telegram_user_id)
    await update.message.reply_text(
        draft or "Черновик за сегодня пока не собран.",
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML if draft else None,
    )


async def cmd_fix_draft(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    instruction = " ".join(context.args).strip()
    if not instruction:
        _set_pending_draft_edit(context, user.telegram_user_id)
        await update.message.reply_text(revision_help_text(), reply_markup=_edit_draft_keyboard())
        return
    await _apply_draft_revision(update, context, user, instruction)


async def cmd_finalize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    repository = _repo(context)
    target_date = _today(context)
    draft = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id)
    style = resolve_style_for_user(_repo(context), user.telegram_user_id)
    if not draft:
        draft = _build_and_store_today_draft_with_style(context, user, style=style)
    finalize_daily_report(repository, target_date, draft, user.telegram_user_id, style=style, language="ru")
    await update.message.reply_text(
        f"<b>Финальный отчет за {target_date.strftime('%d.%m.%Y')} зафиксирован.</b>\n\n{draft}",
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def cmd_show_final(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    final_report = _repo(context).get_latest_final_report_for_date(
        _today(context),
        author_user_id=user.telegram_user_id,
    )
    await update.message.reply_text(
        final_report or "Финальный отчет за сегодня пока не зафиксирован.",
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML if final_report else None,
    )


async def cmd_reprocess(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    processed, resolved = _reprocess_notes_for_today(context, user)
    await update.message.reply_text(
        (
            f"Повторная обработка завершена.\n"
            f"Проверено заметок: {processed}\n"
            f"Автопривязано к проектам: {resolved}"
        ),
        reply_markup=_base_keyboard(),
    )


async def cmd_templates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    templates = _repo(context).list_report_templates(active_only=True)
    selected_key = selected_template_key(_repo(context), user.telegram_user_id)
    if not templates:
        await update.message.reply_text("Шаблоны пока не настроены.", reply_markup=_base_keyboard())
        return
    lines = ["<b>Шаблоны отчетов</b>", ""]
    for template in templates:
        markers: list[str] = []
        if template.is_default:
            markers.append("по умолчанию")
        if selected_key == template.template_key:
            markers.append("выбран")
        lines.append(f"<b>{escape(template.title)}</b>  <code>{escape(template.template_key)}</code>")
        if template.description:
            lines.append(f"- {escape(template.description)}")
        if markers:
            lines.append(f"- <i>{escape(', '.join(markers))}</i>")
        lines.append("")
    lines.append(
        "Выбор: <code>/template standard</code>, <code>/template concise</code>, "
        "<code>/template risk_focus</code>, <code>/template team</code>"
    )
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def cmd_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    key = " ".join(context.args).strip().lower()
    if not key:
        await update.message.reply_text(
            "Укажите ключ шаблона. Пример: `/template concise`",
            reply_markup=_base_keyboard(),
        )
        return
    template = _repo(context).get_report_template(key)
    if template is None or not template.is_active:
        await update.message.reply_text(
            "Не нашел такой шаблон. Используйте `/templates`.",
            reply_markup=_base_keyboard(),
        )
        return
    set_selected_template_key(_repo(context), user.telegram_user_id, template.template_key)
    await update.message.reply_text(
        f"Для вас выбран шаблон: {template.template_key} ({template.title}).",
        reply_markup=_base_keyboard(),
    )


async def cmd_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    args = [arg.strip() for arg in context.args if arg.strip()]
    if not args:
        await update.message.reply_text(
            "Используйте: `/task add <текст>` или `/task done|wait|progress|open <id>`.",
            reply_markup=_base_keyboard(),
        )
        return

    action = args[0].lower()
    repository = _repo(context)

    if action in {"done", "wait", "progress", "open"}:
        if len(args) < 2 or not args[1].isdigit():
            await update.message.reply_text(
                "Укажите id задачи. Пример: `/task done 12`.",
                reply_markup=_base_keyboard(),
            )
            return
        task_id = int(args[1])
        status_map = {
            "done": "done",
            "wait": "waiting",
            "progress": "in_progress",
            "open": "open",
        }
        updated = repository.update_task_status(task_id, user.telegram_user_id, status_map[action])
        if not updated:
            await update.message.reply_text(
                "Не нашел задачу с таким id в вашем списке.",
                reply_markup=_base_keyboard(),
            )
            return
        await _reply_html(
            update.message,
            f"<b>Статус задачи <code>#{task_id}</code> обновлен</b>\n{escape(_human_task_status(status_map[action]))}",
            reply_markup=_base_keyboard(),
        )
        return

    if action != "add":
        await update.message.reply_text(
            "Используйте: `/task add <текст>` или коротко `задача: ...`.",
            reply_markup=_base_keyboard(),
        )
        return

    title = " ".join(args[1:]).strip()
    if not title:
        await update.message.reply_text(
            "Добавьте текст задачи после `add`.",
            reply_markup=_base_keyboard(),
        )
        return

    await _add_task_from_text(update, context, user, title)


async def cmd_mytasks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    repository = _repo(context)
    mode = context.args[0].strip().lower() if context.args else "active"
    if mode == "all":
        statuses = None
    elif mode == "done":
        statuses = ["done"]
    else:
        statuses = ["open", "in_progress", "waiting"]
    tasks = repository.list_tasks_for_user(user.telegram_user_id, statuses=statuses, limit=60)
    if not tasks:
        await update.message.reply_text(
            "Список задач пуст. Добавьте: `/task add ...`",
            reply_markup=_base_keyboard(),
        )
        return
    lines = [f"<b>Follow-up список</b> <i>({escape(mode)})</i>", ""]
    for task in tasks:
        project = repository.get_project(task.project_id) if task.project_id else None
        suffix_parts: list[str] = []
        if project:
            suffix_parts.append(project.name)
        if task.epic:
            suffix_parts.append(f"эпик: {task.epic}")
        if task.jira_key:
            suffix_parts.append(task.jira_key)
        lines.append(
            f"- <code>#{task.id}</code> <b>{escape(_human_task_status(task.status))}</b> {escape(task.title)}"
        )
        if suffix_parts:
            lines.append(f"  {escape(' | '.join(suffix_parts))}")
    lines.append("")
    lines.append("Смена статуса: <code>готово 12</code> или <code>/task done 12</code>")
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def cmd_inbox(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    args = [arg.strip() for arg in context.args if arg.strip()]
    if args and args[0].lower() == "resolve":
        await _resolve_inbox_item(update, context, user, args)
        return

    show_all = bool(args and args[0].lower() == "all")
    target_date = None if show_all else _today(context)
    repository = _repo(context)
    notes = repository.list_unresolved_notes_for_user(
        user.telegram_user_id,
        target_date=target_date,
        limit=30,
    )
    if not notes:
        await update.message.reply_text(
            "Нечего уточнять: все апдейты уже разобраны.",
            reply_markup=_base_keyboard(),
        )
        return

    projects = repository.list_projects(owner_user_id=user.telegram_user_id)
    fallback_ids = fallback_project_ids(repository, owner_user_id=user.telegram_user_id)
    title = "Нужно уточнить (все даты)" if show_all else f"Нужно уточнить за {_today(context).strftime('%d.%m.%Y')}"
    lines = [f"<b>{escape(title)}</b>", ""]
    for note in notes:
        parsed = parse_note_text(note.raw_text, projects)
        resolution = resolve_project_for_block(
            repository=repository,
            block_text=note.raw_text,
            parsed_note=parsed,
            fallback_project_ids=fallback_ids,
            owner_user_id=user.telegram_user_id,
        )
        candidates = project_names_by_ids(
            repository,
            resolution.candidate_project_ids,
            owner_user_id=user.telegram_user_id,
        )[:3]
        lines.append(f"- <code>note#{note.id}</code> <b>{escape(note.note_date)}</b>")
        lines.append(f"  {escape(_truncate_inline(note.raw_text, 90))}")
        if candidates:
            lines.append(f"  <b>Варианты:</b> {escape(', '.join(candidates))}")
    lines.append("")
    lines.append("Resolve: <code>разобрать 15 DC701</code> или <code>/inbox resolve 15 DC701</code>")
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def cmd_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    projects = _repo(context).list_projects(owner_user_id=user.telegram_user_id)
    if not projects:
        await update.message.reply_text("Справочник проектов пока пустой.", reply_markup=_base_keyboard())
        return
    lines = ["<b>Справочник проектов</b>", ""]
    for project in projects:
        aliases = ", ".join(project.aliases) if project.aliases else "-"
        mode = "особый контроль" if project.is_special_control else "общий"
        lines.append(f"- <b>{escape(project.name)}</b>")
        lines.append(f"  <b>Менеджер:</b> {escape(project.manager_name or '-')}")
        lines.append(f"  <b>Руководитель:</b> {escape(project.lead_name or '-')}")
        lines.append(f"  <b>Алиасы:</b> {escape(aliases)}")
        lines.append(f"  <b>Режим:</b> {escape(mode)}")
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def cmd_epics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    epics = _repo(context).list_epics(owner_user_id=user.telegram_user_id)
    if not epics:
        await update.message.reply_text(
            "Реестр эпиков пока пустой. Можно добавить так: `эпик: Caller ID | проект: Онбординг`.",
            reply_markup=_base_keyboard(),
        )
        return
    lines = ["<b>Эпики</b>", ""]
    for epic in epics[:40]:
        project = _repo(context).get_project(epic.project_id, owner_user_id=user.telegram_user_id)
        lines.append(
            f"- <b>{escape(epic.name)}</b> -> {escape(project.name if project else 'Без проекта')}"
        )
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


async def on_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    text = update.message.text.strip()
    if text in {BTN_STATUS, "Статус"}:
        await cmd_status(update, context)
        return
    if text in {BTN_BUILD_DRAFT, "Собрать отчет", "Собрать отчёт"}:
        style = resolve_style_for_user(_repo(context), user.telegram_user_id)
        content = _build_and_store_today_draft_with_style(context, user, style=style)
        await update.message.reply_text(content, reply_markup=_base_keyboard(), parse_mode=ParseMode.HTML)
        return
    if text == BTN_PRO:
        await cmd_pro(update, context)
        return
    if text == BTN_SHOW_DRAFT:
        await cmd_show_draft(update, context)
        return
    if text in {BTN_MY_TASKS, "Мои задачи"}:
        await cmd_mytasks(update, context)
        return
    if text == BTN_INBOX:
        await cmd_inbox(update, context)
        return
    if text == BTN_FINALIZE:
        await cmd_finalize(update, context)
        return
    if text == BTN_SHOW_FINAL:
        await cmd_show_final(update, context)
        return
    if text == BTN_EDIT_DRAFT:
        _set_pending_draft_edit(context, user.telegram_user_id)
        await update.message.reply_text(revision_help_text(), reply_markup=_edit_draft_keyboard())
        return
    if await _handle_pending_draft_revision(update, context, user, text):
        return
    if await _handle_project_config_message(update, context, user, text):
        return
    if await _handle_epic_config_message(update, context, user, text):
        return
    if await _handle_profile_settings_message(update, context, user, text):
        return
    if await _handle_last_note_correction(update, context, user, text):
        return
    if await _handle_pending_project_resolution(update, context, user, text):
        return
    if await _handle_smart_input(update, context, user, text):
        return

    results = _store_notes(text, source="text_message", context=context, user=user)
    await update.message.reply_text(
        render_captured_notes_message(results),
        reply_markup=_reply_markup_for_results(results),
        parse_mode=ParseMode.HTML,
    )


async def on_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.voice or not update.effective_user:
        return
    user = _sync_user_profile(update, context)
    voice = update.message.voice
    voice_file = await voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".ogg") as temp_file:
        temp_path = Path(temp_file.name)
    await voice_file.download_to_drive(custom_path=str(temp_path))

    transcription = _transcription(context).transcribe(temp_path)
    temp_path.unlink(missing_ok=True)
    if not transcription:
        fallback_text = (
            f"voice-note: transcription failed; duration={voice.duration}s; "
            f"file_id={voice.file_unique_id or voice.file_id}"
        )
        results = _store_notes(
            fallback_text,
            source="voice_failed",
            context=context,
            user=user,
            transcript_text="",
        )
        await update.message.reply_text(
            (
                f"{render_captured_notes_message(results)}\n"
                "Voice не распознался, но заметку я сохранил. "
                "Можно прислать текстом уточнение одним сообщением."
            ),
            reply_markup=_reply_markup_for_results(results),
            parse_mode=ParseMode.HTML,
        )
        return
    results = _store_notes(
        transcription,
        source="voice",
        context=context,
        user=user,
        transcript_text=transcription,
    )
    await update.message.reply_text(
        f"{render_captured_notes_message(results)}\n<b>Транскрипт:</b> {escape(transcription)}",
        reply_markup=_reply_markup_for_results(results),
        parse_mode=ParseMode.HTML,
    )


async def send_daily_draft_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = _settings(context)
    now = datetime.now(ZoneInfo(settings.timezone))
    if now.weekday() > 4:
        return
    repository = _repo(context)
    if settings.owner_user_id is None:
        return
    user = repository.get_user(settings.owner_user_id)
    if user is None:
        return
    content = _build_and_store_today_draft_with_style(
        context,
        user,
        style=default_template_style(_repo(context)),
    )
    await context.bot.send_message(
        chat_id=user.telegram_user_id,
        text=content,
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def _handle_profile_settings_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message:
        return False
    lowered = text.lower()
    if lowered.startswith("менеджер:"):
        value = text.split(":", 1)[1].strip()
        if not value:
            await update.message.reply_text("После `менеджер:` укажите ФИО.", reply_markup=_base_keyboard())
            return True
        user = _repo(context).update_user_defaults(user.telegram_user_id, default_manager_name=value)
        await update.message.reply_text(
            f"Сохранил менеджера по умолчанию: {user.default_manager_name}.",
            reply_markup=_base_keyboard(),
        )
        return True
    if lowered.startswith("руководитель:"):
        value = text.split(":", 1)[1].strip()
        if not value:
            await update.message.reply_text("После `руководитель:` укажите ФИО.", reply_markup=_base_keyboard())
            return True
        user = _repo(context).update_user_defaults(user.telegram_user_id, default_lead_name=value)
        await update.message.reply_text(
            f"Сохранил руководителя по умолчанию: {user.default_lead_name}.",
            reply_markup=_base_keyboard(),
        )
        return True
    return False


async def _handle_project_config_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message or not text.lower().startswith("проект:"):
        return False
    payload = parse_project_definition(text)
    if not payload["name"]:
        await update.message.reply_text(
            "Используйте формат `проект: Название | менеджер: ... | руководитель: ...`.",
            reply_markup=_base_keyboard(),
        )
        return True

    repository = _repo(context)
    existing = repository.find_project_by_name_or_alias(payload["name"], owner_user_id=user.telegram_user_id)
    aliases = payload["aliases"] or (existing.aliases if existing else [payload["name"]])
    manager_name = payload["manager_name"] or (existing.manager_name if existing else "") or resolve_manager_name(
        None, user, _settings(context)
    )
    lead_name = payload["lead_name"] or (existing.lead_name if existing else "") or resolve_lead_name(
        None, user, _settings(context)
    )
    jira_base_url = payload["jira_base_url"] or (existing.jira_base_url if existing else "")
    is_special_control = payload["is_special_control"] if payload["has_special_control"] else (
        existing.is_special_control if existing else False
    )
    project = repository.upsert_project(
        name=payload["name"],
        manager_name=manager_name,
        lead_name=lead_name,
        jira_base_url=jira_base_url,
        aliases=aliases,
        is_special_control=is_special_control,
        owner_user_id=user.telegram_user_id,
    )

    pending_note_id = _get_pending_note_id(context, user.telegram_user_id)
    note_suffix = ""
    if pending_note_id is not None:
        repository.update_note_project(
            pending_note_id,
            project,
            resolve_manager_name(project, user, _settings(context)),
            resolve_lead_name(project, user, _settings(context)),
        )
        _clear_pending_note_id(context, user.telegram_user_id)
        note_suffix = "\nИ сразу привязал к этому проекту последнюю неуточненную заметку."

    await update.message.reply_text(
        (
            f"Проект сохранен: {project.name}\n"
            f"Менеджер: {project.manager_name or '-'}\n"
            f"Руководитель: {project.lead_name or '-'}\n"
            f"Особый контроль: {'да' if project.is_special_control else 'нет'}"
            f"{note_suffix}"
        ),
        reply_markup=_base_keyboard(),
    )
    return True


async def _handle_epic_config_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message or not text.lower().startswith("эпик:"):
        return False
    payload = parse_epic_definition(text)
    epic_name = payload["epic_name"]
    project_name = payload["project_name"]
    if not epic_name or not project_name:
        await update.message.reply_text(
            "Используйте формат: `эпик: Caller ID | проект: Онбординг | алиасы: caller, caller id`.",
            reply_markup=_base_keyboard(),
        )
        return True

    project, created_project = resolve_or_create_project(project_name, _repo(context), user, _settings(context))
    epic = _repo(context).upsert_epic(
        project_id=project.id,
        name=epic_name,
        aliases=payload["aliases"] or [epic_name],
        source="manual",
    )
    if epic is None:
        await update.message.reply_text("Не удалось сохранить эпик.", reply_markup=_base_keyboard())
        return True

    pending_note_id = _get_pending_note_id(context, user.telegram_user_id)
    note_suffix = ""
    project_suffix = "\nПроект создан автоматически." if created_project else ""
    if pending_note_id is not None:
        _repo(context).update_note_project(
            pending_note_id,
            project,
            resolve_manager_name(project, user, _settings(context)),
            resolve_lead_name(project, user, _settings(context)),
        )
        _repo(context).update_note_epic(pending_note_id, epic.name)
        _clear_pending_note_id(context, user.telegram_user_id)
        note_suffix = "\nПоследнюю неуточненную заметку сразу связал с этим эпиком."

    await update.message.reply_text(
        (
            f"Эпик сохранен: {epic.name}\n"
            f"Проект: {project.name}"
            f"{project_suffix}"
            f"{note_suffix}"
        ),
        reply_markup=_base_keyboard(),
    )
    return True


async def _handle_last_note_correction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message:
        return False
    match = CORRECTION_RE.match(text)
    if not match:
        return False
    latest_note = _repo(context).get_latest_note_for_user(user.telegram_user_id)
    if latest_note is None:
        return False
    replacement = match.group(2).strip()
    existing = _repo(context).find_project_by_name_or_alias(replacement, owner_user_id=user.telegram_user_id)
    if existing is None and not looks_like_project_name(replacement):
        await update.message.reply_text(
            "Исправление понял, но название проекта слишком размытое. Лучше ответьте так: "
            "`проект: Название | руководитель: Имя Фамилия`.",
            reply_markup=_base_keyboard(),
        )
        return True
    project, created = resolve_or_create_project(replacement, _repo(context), user, _settings(context))
    manager_name = resolve_manager_name(project, user, _settings(context))
    lead_name = resolve_lead_name(project, user, _settings(context))
    _repo(context).update_note_project(latest_note.id, project, manager_name, lead_name)
    if _get_pending_note_id(context, user.telegram_user_id) == latest_note.id:
        _clear_pending_note_id(context, user.telegram_user_id)
    message = f"Исправил последнюю заметку: проект `{project.name}`."
    if created:
        message += "\nНовый проект сразу добавил в справочник."
    await update.message.reply_text(message, reply_markup=_base_keyboard())
    return True


async def _handle_pending_project_resolution(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message:
        return False
    pending_note_id = _get_pending_note_id(context, user.telegram_user_id)
    if pending_note_id is None:
        return False
    if text == BTN_SKIP:
        _clear_pending_note_id(context, user.telegram_user_id)
        await update.message.reply_text(
            "Ок, оставил последнюю заметку без проекта. Можно вернуться к ней позже.",
            reply_markup=_base_keyboard(),
        )
        return True

    project = _repo(context).find_project_by_name_or_alias(text, owner_user_id=user.telegram_user_id)
    created = False
    if project is None:
        if not looks_like_project_name(text):
            await update.message.reply_text(
                "Не смог понять проект. Выберите его кнопкой или ответьте сообщением `проект: Название`.",
                reply_markup=_clarification_keyboard(
                    project_names_by_ids(
                        _repo(context),
                        fallback_project_ids(_repo(context), owner_user_id=user.telegram_user_id),
                        owner_user_id=user.telegram_user_id,
                    )
                ),
            )
            return True
        project, created = resolve_or_create_project(text, _repo(context), user, _settings(context))
    manager_name = resolve_manager_name(project, user, _settings(context))
    lead_name = resolve_lead_name(project, user, _settings(context))
    _repo(context).update_note_project(pending_note_id, project, manager_name, lead_name)
    _clear_pending_note_id(context, user.telegram_user_id)

    message = (
        f"Привязал заметку к проекту `{project.name}`.\n"
        f"Менеджер: {manager_name or '-'}\n"
        f"Руководитель: {lead_name or '-'}"
    )
    if created:
        message += "\nПроект новый, поэтому я добавил его в справочник автоматически."
    await update.message.reply_text(message, reply_markup=_base_keyboard())
    return True


async def _handle_pending_draft_revision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    if not update.message or not _has_pending_draft_edit(context, user.telegram_user_id):
        return False
    await _apply_draft_revision(update, context, user, text)
    return True


async def _handle_smart_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    text: str,
) -> bool:
    action = parse_smart_input(text)
    if action is None:
        return False
    return await _run_smart_input_action(update, context, user, action)


async def _run_smart_input_action(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    action: SmartInputAction,
) -> bool:
    if action.kind == "status":
        await cmd_status(update, context)
        return True
    if action.kind == "mytasks":
        context.args = []
        await cmd_mytasks(update, context)
        return True
    if action.kind == "inbox":
        context.args = []
        await cmd_inbox(update, context)
        return True
    if action.kind == "show_draft":
        await cmd_show_draft(update, context)
        return True
    if action.kind == "show_final":
        await cmd_show_final(update, context)
        return True
    if action.kind == "add_task":
        await _add_task_from_text(update, context, user, action.text)
        return True
    if action.kind in {"task_done", "task_waiting", "task_progress", "task_open"}:
        if action.task_id is None:
            return False
        status_map = {
            "task_done": "done",
            "task_waiting": "waiting",
            "task_progress": "in_progress",
            "task_open": "open",
        }
        updated = _repo(context).update_task_status(action.task_id, user.telegram_user_id, status_map[action.kind])
        if not updated and update.message:
            await update.message.reply_text(
                "Не нашел задачу с таким id в вашем списке.",
                reply_markup=_base_keyboard(),
            )
        elif update.message:
            await _reply_html(
                update.message,
                f"<b>Статус задачи <code>#{action.task_id}</code> обновлен</b>\n"
                f"{escape(_human_task_status(status_map[action.kind]))}",
                reply_markup=_base_keyboard(),
            )
        return True
    if action.kind == "resolve_inbox":
        args = ["resolve", str(action.task_id or 0), action.project_name]
        await _resolve_inbox_item(update, context, user, args)
        return True
    return False


async def _apply_draft_revision(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    instruction: str,
) -> None:
    if not update.message:
        return
    revision = parse_revision_instruction(instruction)
    if revision is None:
        await update.message.reply_text(
            f"Не понял вариант правки. {revision_help_text()}",
            reply_markup=_edit_draft_keyboard(),
        )
        return
    content = _build_and_store_today_draft_with_style(context, user, style=revision.style)
    _clear_pending_draft_edit(context, user.telegram_user_id)
    await update.message.reply_text(
        f"<b>Черновик пересобран:</b> {revision.label}\n\n{content}",
        reply_markup=_base_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def _add_task_from_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    title: str,
) -> None:
    if not update.message:
        return
    repository = _repo(context)
    projects = repository.list_projects(owner_user_id=user.telegram_user_id)
    parsed = parse_note_text(title, projects)
    resolution = resolve_project_for_block(
        repository=repository,
        block_text=title,
        parsed_note=parsed,
        fallback_project_ids=fallback_project_ids(repository, owner_user_id=user.telegram_user_id),
        owner_user_id=user.telegram_user_id,
    )
    task_id = repository.add_task(
        NewPMTask(
            owner_user_id=user.telegram_user_id,
            title=title,
            project_id=resolution.project_id,
            epic=parsed.epic,
            jira_key=_extract_first_task_jira_key(title),
            jira_url=parsed.jira_links[0] if parsed.jira_links else "",
            status="open",
            source="manual",
        )
    )
    project = repository.get_project(resolution.project_id, owner_user_id=user.telegram_user_id) if resolution.project_id else None
    lines = [
        f"<b>Задача <code>#{task_id}</code> добавлена</b>",
        "",
        f"<b>Текст:</b> {escape(title)}",
        f"<b>Проект:</b> {escape(project.name if project else 'Не определен')}",
    ]
    if parsed.epic:
        lines.append(f"<b>Эпик:</b> {escape(parsed.epic)}")
    if project is None and resolution.candidate_project_ids:
        lines.append(
            f"<b>Возможные проекты:</b> "
            f"{escape(', '.join(project_names_by_ids(repository, resolution.candidate_project_ids, owner_user_id=user.telegram_user_id)))}"
        )
    await _reply_html(update.message, "\n".join(lines), reply_markup=_base_keyboard())


def _store_notes(
    raw_text: str,
    source: str,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    transcript_text: str = "",
) -> list[StoredNoteResult]:
    results, unresolved_note_ids = capture_notes(
        repository=_repo(context),
        settings=_settings(context),
        raw_text=raw_text,
        note_date=_today(context).isoformat(),
        source=source,
        user=user,
        transcript_text=transcript_text,
    )
    if unresolved_note_ids:
        _set_pending_note_id(context, user.telegram_user_id, unresolved_note_ids[-1])
    else:
        _clear_pending_note_id(context, user.telegram_user_id)
    return results


def _reprocess_notes_for_today(context: ContextTypes.DEFAULT_TYPE, user: UserProfile) -> tuple[int, int]:
    repository = _repo(context)
    settings = _settings(context)
    notes = repository.list_notes_for_user_on_date(user.telegram_user_id, _today(context))
    projects = repository.list_projects(owner_user_id=user.telegram_user_id)
    fallback_ids = fallback_project_ids(repository, owner_user_id=user.telegram_user_id)
    processed = 0
    resolved = 0
    for note in notes:
        if not note.needs_review:
            continue
        parsed = parse_note_text(note.raw_text, projects)
        resolution = resolve_project_for_block(
            repository=repository,
            block_text=note.raw_text,
            parsed_note=parsed,
            fallback_project_ids=fallback_ids,
            owner_user_id=user.telegram_user_id,
        )
        project = repository.get_project(resolution.project_id, owner_user_id=user.telegram_user_id) if resolution.project_id else None
        manager_name = resolve_manager_name(project, user, settings)
        lead_name = resolve_lead_name(project, user, settings)
        repository.update_note_analysis(
            note_id=note.id,
            project_id=resolution.project_id,
            manager_name=manager_name,
            lead_name=lead_name,
            epic=parsed.epic,
            status_text=parsed.status_text,
            done_text=parsed.done_text,
            plan_text=parsed.plan_text,
            risk_text=parsed.risk_text,
            jira_links=parsed.jira_links,
            needs_review=resolution.project_id is None,
        )
        if project is not None and parsed.epic:
            repository.upsert_epic(project.id, parsed.epic, aliases=[parsed.epic], source="note-reprocess")
        processed += 1
        if resolution.project_id is not None:
            resolved += 1
    return processed, resolved


async def _resolve_inbox_item(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    args: list[str],
) -> None:
    if not update.message:
        return
    if len(args) < 3 or not args[1].isdigit():
        await update.message.reply_text(
            "Формат: `/inbox resolve <note_id> <проект>`.",
            reply_markup=_base_keyboard(),
        )
        return
    note_id = int(args[1])
    project_name = " ".join(args[2:]).strip()
    if not project_name:
        await update.message.reply_text(
            "После id укажите название проекта.",
            reply_markup=_base_keyboard(),
        )
        return
    repository = _repo(context)
    note = repository.get_note(note_id)
    if note is None or note.user_id != user.telegram_user_id:
        await update.message.reply_text(
            "Не нашел такую заметку в вашем inbox.",
            reply_markup=_base_keyboard(),
        )
        return
    project = repository.find_project_by_name_or_alias(project_name, owner_user_id=user.telegram_user_id)
    created = False
    if project is None:
        if not looks_like_project_name(project_name):
            await update.message.reply_text(
                "Название проекта слишком неявное. Укажите точнее.",
                reply_markup=_base_keyboard(),
            )
            return
        project, created = resolve_or_create_project(project_name, _repo(context), user, _settings(context))
    manager_name = resolve_manager_name(project, user, _settings(context))
    lead_name = resolve_lead_name(project, user, _settings(context))
    repository.update_note_project(note_id, project, manager_name, lead_name)
    if _get_pending_note_id(context, user.telegram_user_id) == note_id:
        _clear_pending_note_id(context, user.telegram_user_id)
    msg = f"<b>Готово:</b> <code>note#{note_id}</code> привязана к проекту <b>{escape(project.name)}</b>."
    if created:
        msg += "\nПроект добавлен в справочник автоматически."
    await _reply_html(update.message, msg, reply_markup=_base_keyboard())


# task_status_label() is imported from shared.py
_human_task_status = task_status_label


def _extract_first_task_jira_key(text: str) -> str:
    match = TASK_JIRA_KEY_RE.search(text)
    return match.group(1).upper() if match else ""


def _truncate_inline(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _reply_markup_for_results(results: list[StoredNoteResult]) -> ReplyKeyboardMarkup:
    unresolved = [result for result in results if result.needs_review]
    if len(unresolved) == 1:
        return _clarification_keyboard(unresolved[0].candidate_names)
    return _base_keyboard()


def _build_and_store_today_draft(context: ContextTypes.DEFAULT_TYPE, user: UserProfile) -> str:
    return _build_and_store_today_draft_with_style(
        context,
        user,
        style=default_template_style(_repo(context)),
    )


def _build_and_store_today_draft_with_style(
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    style: str,
) -> str:
    return build_and_store_daily_draft(
        repository=_repo(context),
        settings=_settings(context),
        target_date=_today(context),
        user_id=user.telegram_user_id,
        style=style,
    )


def _build_status_message(context: ContextTypes.DEFAULT_TYPE, user: UserProfile) -> str:
    repository = _repo(context)
    target_date = _today(context)
    notes = repository.list_notes_for_user_on_date(user.telegram_user_id, target_date)
    group_labels: set[str] = set()
    for note in notes:
        if note.project_id:
            project = repository.get_project(note.project_id, owner_user_id=user.telegram_user_id)
            if project is not None:
                group_labels.add(project.name)
                continue
        if note.epic.strip():
            group_labels.add(note.epic.strip())
    unresolved = repository.list_unresolved_notes_for_user(user.telegram_user_id, target_date=target_date, limit=100)
    tasks = repository.list_tasks_for_user(
        user.telegram_user_id,
        statuses=["open", "in_progress", "waiting"],
        limit=100,
    )
    draft_exists = repository.get_latest_draft_for_date(target_date, owner_user_id=user.telegram_user_id) is not None
    final_exists = (
        repository.get_latest_final_report_for_date(target_date, author_user_id=user.telegram_user_id) is not None
    )
    recommendation = _status_recommendation(
        note_count=len(notes),
        unresolved_count=len(unresolved),
        task_count=len(tasks),
        draft_exists=draft_exists,
        final_exists=final_exists,
    )
    lines = [
        f"<b>Статус дня за {target_date.strftime('%d.%m.%Y')}</b>",
        "",
        "<b>Что уже собрано</b>",
        f"- Апдейтов: <code>{len(notes)}</code>",
        f"- Проектов / эпиков: <code>{len(group_labels)}</code>",
        f"- Нужно уточнить: <code>{len(unresolved)}</code>",
        f"- Follow-up задач: <code>{len(tasks)}</code>",
        f"- Черновик: <b>{'есть' if draft_exists else 'нет'}</b>",
        f"- Финальный: <b>{'есть' if final_exists else 'нет'}</b>",
        "",
        "<b>Следующий шаг</b>",
        recommendation,
    ]
    return "\n".join(lines)


def _status_recommendation(
    note_count: int,
    unresolved_count: int,
    task_count: int,
    draft_exists: bool,
    final_exists: bool,
) -> str:
    if unresolved_count:
        return "Откройте <code>inbox</code> и разберите апдейты, где система не уверена в проекте."
    if note_count and not draft_exists:
        return "Нажмите <b>📋 Собрать отчёт</b> или используйте <code>/draft</code>, чтобы собрать digest."
    if draft_exists and not final_exists:
        return "Проверьте текст и зафиксируйте финальный отчет."
    if task_count:
        return "Проверьте follow-up список и обновите статусы фразами вроде <code>готово 12</code>."
    return "Можно продолжать добавлять апдейты или задачи через <code>задача: ...</code>."


async def _reply_html(message, text: str, reply_markup: ReplyKeyboardMarkup | None = None) -> None:
    if message is None:
        return
    await message.reply_text(
        text,
        reply_markup=reply_markup or _base_keyboard(),
        parse_mode=ParseMode.HTML,
    )


async def _maybe_send_mini_app_entry(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user: UserProfile,
    force_message: bool = False,
) -> None:
    if not update.message or not update.effective_chat:
        return
    url = _mini_app_url(_settings(context))
    if not url:
        if force_message:
            await update.message.reply_text(
                "Mini App пока не настроен. Укажите PUBLIC_WEB_APP_URL с HTTPS-адресом приложения.",
                reply_markup=_base_keyboard(),
            )
        return

    try:
        await context.bot.set_chat_menu_button(
            chat_id=update.effective_chat.id,
            menu_button=MenuButtonWebApp(text="Mini App", web_app=WebAppInfo(url=url)),
        )
    except Exception:
        pass

    launch_markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Открыть Mini App", web_app=WebAppInfo(url=url))]]
    )
    await update.message.reply_text(
        (
            "<b>Mini App готов</b>\n"
            f"Автор подтянется как <b>{escape(user.display_name or user.telegram_full_name)}</b>, "
            "а ваши проекты, апдейты и отчеты будут изолированы от других пользователей."
        ),
        reply_markup=launch_markup,
        parse_mode=ParseMode.HTML,
    )


def _sync_user_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> UserProfile:
    effective_user = update.effective_user
    if effective_user is None:
        raise RuntimeError("Expected effective_user in update")
    repository = _repo(context)
    profile = repository.upsert_user(
        telegram_user_id=effective_user.id,
        telegram_username=effective_user.username or "",
        telegram_full_name=effective_user.full_name or effective_user.username or str(effective_user.id),
    )
    display_name = profile.display_name or profile.telegram_full_name
    manager_name = profile.default_manager_name or display_name
    if display_name != profile.display_name or manager_name != profile.default_manager_name:
        profile = repository.update_user_defaults(
            profile.telegram_user_id,
            display_name=display_name,
            default_manager_name=manager_name,
        )
    return profile


def _mini_app_url(settings: Settings) -> str:
    url = settings.public_web_app_url.strip()
    if not url.startswith("https://"):
        return ""
    return url


# resolve_or_create_project is imported from project_resolution.py
# resolve_manager_name / resolve_lead_name are imported from project_resolution.py


def _pending_key(user_id: int) -> str:
    return f"pending_note:{user_id}"


def _pending_draft_key(user_id: int) -> str:
    return f"pending_draft_edit:{user_id}"


def _set_pending_note_id(context: ContextTypes.DEFAULT_TYPE, user_id: int, note_id: int) -> None:
    _repo(context).set_state(_pending_key(user_id), str(note_id))


def _get_pending_note_id(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> int | None:
    raw_value = _repo(context).get_state(_pending_key(user_id))
    if not raw_value:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _clear_pending_note_id(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    _repo(context).delete_state(_pending_key(user_id))


def _set_pending_draft_edit(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    _repo(context).set_state(_pending_draft_key(user_id), "1")


def _has_pending_draft_edit(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    return _repo(context).get_state(_pending_draft_key(user_id)) == "1"


def _clear_pending_draft_edit(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    _repo(context).delete_state(_pending_draft_key(user_id))


def _base_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [BTN_BUILD_DRAFT, BTN_STATUS],
            [BTN_MY_TASKS, BTN_PRO],
        ],
        resize_keyboard=True,
    )


def _edit_draft_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["короче", "акцент на риск"], ["командный", "обычный"], [BTN_BUILD_DRAFT, BTN_STATUS]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _clarification_keyboard(candidate_names: list[str]) -> ReplyKeyboardMarkup:
    names = [name for name in candidate_names if name][:4]
    rows: list[list[str]] = []
    for index in range(0, len(names), 2):
        rows.append(names[index : index + 2])
    rows.append([BTN_SKIP])
    rows.append([BTN_BUILD_DRAFT, BTN_STATUS])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)


def _today(context: ContextTypes.DEFAULT_TYPE):
    return today_date(_settings(context))


def _settings(context: ContextTypes.DEFAULT_TYPE) -> Settings:
    return context.application.bot_data["settings"]


def _repo(context: ContextTypes.DEFAULT_TYPE) -> Repository:
    return context.application.bot_data["repository"]


def _transcription(context: ContextTypes.DEFAULT_TYPE) -> TranscriptionService:
    return context.application.bot_data["transcription"]


def _admin(context: ContextTypes.DEFAULT_TYPE) -> AdminService:
    settings = _settings(context)
    repository = _repo(context)
    return AdminService(repository.db, settings)


def _check_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Возвращает True если вызывающий — super admin. Иначе отвечает отказом."""
    username = (update.effective_user.username or "") if update.effective_user else ""
    if _admin(context).is_super_admin(username):
        return True
    if update.message:
        update.message.reply_text("⛔ Нет доступа.")
    return False


async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать статистику платформы. Только для super admin."""
    if not update.message or not update.effective_user:
        return
    if not _check_admin(update, context):
        return
    svc = _admin(context)
    stats = svc.get_platform_stats()
    text = svc.format_stats_message(stats)
    await _reply_html(update.message, text)


async def cmd_admin_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/adminuser @username_или_id — найти пользователя."""
    if not update.message or not update.effective_user:
        return
    if not _check_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text(
            "Использование: /adminuser @username или /adminuser 123456789"
        )
        return
    query = context.args[0]
    svc = _admin(context)
    user = svc.find_user(query)
    if not user:
        await update.message.reply_text(f"Пользователь {query} не найден.")
        return
    text = svc.format_user_message(user)
    await _reply_html(update.message, text)


async def cmd_grant_pro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/grantpro @username [месяцы] — выдать PRO подписку."""
    if not update.message or not update.effective_user:
        return
    if not _check_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Использование: /grantpro @username [1]")
        return
    svc = _admin(context)
    query = context.args[0]
    months = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    user = svc.find_user(query)
    if not user:
        await update.message.reply_text(f"Пользователь {query} не найден.")
        return
    svc.grant_pro(user.telegram_user_id, months)
    await _reply_html(
        update.message,
        f"⭐ <b>PRO выдан</b> пользователю "
        f"<code>{user.telegram_user_id}</code> на <b>{months} мес.</b>"
    )


async def cmd_grant_team(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/grantteam @username [месяцы] — выдать TEAM подписку."""
    if not update.message or not update.effective_user:
        return
    if not _check_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Использование: /grantteam @username [1]")
        return
    svc = _admin(context)
    query = context.args[0]
    months = int(context.args[1]) if len(context.args) > 1 and context.args[1].isdigit() else 1
    user = svc.find_user(query)
    if not user:
        await update.message.reply_text(f"Пользователь {query} не найден.")
        return
    svc.grant_team(user.telegram_user_id, months)
    await _reply_html(
        update.message,
        f"👥 <b>TEAM выдан</b> пользователю "
        f"<code>{user.telegram_user_id}</code> на <b>{months} мес.</b>"
    )


async def cmd_revoke_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/revokeplan @username — отозвать подписку."""
    if not update.message or not update.effective_user:
        return
    if not _check_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Использование: /revokeplan @username")
        return
    svc = _admin(context)
    query = context.args[0]
    user = svc.find_user(query)
    if not user:
        await update.message.reply_text(f"Пользователь {query} не найден.")
        return
    svc.revoke_subscription(user.telegram_user_id)
    await _reply_html(
        update.message,
        f"🔻 Подписка пользователя <code>{user.telegram_user_id}</code> отозвана → Free."
    )
