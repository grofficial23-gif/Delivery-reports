# ТЗ: PM Digest Design V2

## 1. Назначение документа

Этот документ фиксирует новый визуальный и UX-слой `PM Digest / Delivery Reports`.

Важно разделить версии:

- `V1` — текущая рабочая версия MVP в коде. Ее не удаляем и считаем точкой отката.
- `V2` — новый дизайн-направление по скриншотам и HTML-прототипу: premium dashboard, спиральная анимация, темы, более сильные метрики, профиль, админка и продуктовая подача.

Цель этапа: сначала согласовать визуальный макет и техническое ТЗ, потом переносить в рабочий Mini App без поломки текущей логики.

## 2. Источники V2

### Скриншоты

- `основной дизайн.png` — главный dark premium dashboard.
- `Дизайн тем.png` — сравнение dark / light для одной композиции.
- `дизайн светлой темы.png` — light dashboard на lime palette.
- `Тоже прикольный дизайн синий.png` — светло-синяя wave-тема как дополнительный визуальный режим.

### HTML-референс

- `/Users/grafk1n/<!DOCTYPE html>.html`

Текущий HTML уже содержит:

- 3-колоночный desktop layout;
- левую панель системных статусов;
- центральную canvas-анимацию DNA/spiral;
- правую панель аналитики и метрик;
- нижний статус-бар;
- primary CTA `Собрать отчет`;
- декоративное ускорение анимации при нажатии на CTA.

## 3. Продуктовая идея V2

V2 должен выглядеть как умная операционная панель PM-а:

- слева: состояние системы и данных;
- центр: главный сценарий и визуальная “нервная система” продукта;
- справа: метрики, качество сборки отчета, аналитика;
- снизу: быстрые действия и технический статус;
- сверху: бренд, навигация, тариф, тема, профиль.

Главная мысль интерфейса:

> messy updates -> structured delivery reports

Визуал должен быть дорогим, но не мешать PM-рутине.

## 4. Версионность дизайна

### V1 Current MVP

Текущая версия остается рабочей:

- форма быстрого апдейта;
- список сегодняшних заметок;
- tasks;
- inbox / resolve;
- preview + Telegram text;
- отправка себе в Telegram;
- финализация отчета;
- базовая админка и тарифы.

V1 нужен как safe rollback.

### V2 Target

Новая версия должна сохранить всю функциональность V1, но изменить подачу:

- dashboard first;
- premium visual shell;
- animated spiral core;
- multiple themes;
- stronger profile/admin/subscription surface;
- compact cards instead of длинных простыней;
- report workflow в модальных/нижних панелях или раскрывающихся секциях.

## 5. Темы

### Theme 1: `dark-lime`

Главная тема.

Характер:

- черный фон;
- lime neon accents;
- glass cards;
- glow вокруг CTA и активных элементов;
- бело-серые частицы спирали;
- ощущение enterprise cockpit.

Токены:

- `bg`: `#050607`
- `surface`: `rgba(12, 14, 12, 0.72)`
- `surface-strong`: `rgba(18, 20, 18, 0.88)`
- `text`: `#f7f7f4`
- `muted`: `#9ca3af`
- `primary`: `#a3e635`
- `primary-strong`: `#84cc16`
- `border`: `rgba(255, 255, 255, 0.14)`
- `glow`: `rgba(163, 230, 53, 0.42)`

### Theme 2: `light-lime`

Светлая версия главной темы.

Характер:

- белый / почти белый фон;
- серые тонкие линии;
- lime accents;
- мягкие карточки;
- спираль светлая, воздушная.

Токены:

- `bg`: `#f8fafc`
- `surface`: `#ffffff`
- `surface-soft`: `#f4f7f2`
- `text`: `#111827`
- `muted`: `#6b7280`
- `primary`: `#a3e635`
- `primary-strong`: `#84cc16`
- `border`: `#e5e7eb`
- `glow`: `rgba(132, 204, 22, 0.24)`

### Theme 3: `wave-blue`

Дополнительная тема.

Характер:

- светлый медицинский / AI dashboard;
- blue primary;
- air glass;
- мягкие голубые линии;
- подходит для демо SaaS/enterprise, если lime кажется слишком агрессивным.

Токены:

- `bg`: `#f8fbff`
- `surface`: `rgba(255, 255, 255, 0.84)`
- `text`: `#1e2f4a`
- `muted`: `#718096`
- `primary`: `#2f7dff`
- `primary-strong`: `#0f62fe`
- `border`: `#dbeafe`
- `glow`: `rgba(47, 125, 255, 0.22)`

## 6. Основной экран V2

### Header

Состав:

- логотип `PM DIGEST`;
- subtitle `DELIVERY REPORTS`;
- nav: `Dashboard`, `Reports`, `Analytics`, `Integrations`, `Settings`;
- badge тарифа: `FREE`, `PRO`, `TEAM`;
- переключатель темы;
- профиль пользователя.

Техническая привязка:

- имя пользователя: `user.display_name`;
- роль: `Администратор`, `PM`, `Team owner`;
- тариф: `user_plan`;
- admin link показывать только `is_super_admin` или `team`.

### Центральная сцена

Состав:

- canvas spiral / DNA;
- подпись: `Turn messy updates into structured delivery reports`;
- callouts:
  - `Input data`: количество заметок сегодня;
  - `Structured status`: качество/готовность отчета;
  - `Data flow`: проекты/апдейты;
  - `AI processing`: процент разобранных заметок.

Техническая привязка:

- `summary.notes_count`;
- `summary.project_count`;
- `summary.inbox_count`;
- `summary.draft_chunks`;
- `summary.has_draft`;
- расчет `structured_status`:
  - `0 заметок` -> `0%`
  - `есть inbox` -> `70-85%`
  - `есть draft без inbox` -> `91-98%`
  - `есть final` -> `100%`

### Left rail / System status

Состав:

- `System Online`;
- `System status`;
- вертикальная timeline `01`;
- quick source icons: Telegram, Slack, Google/Jira placeholder.

Техническая привязка:

- Telegram доступность: есть `TELEGRAM_BOT_TOKEN`;
- DB status: health route;
- note capture: `notes_count`;
- security: всегда “Local-first / user scoped” для MVP.

### Cards

Основные карточки:

- `Input Data`: notes today;
- `Structured Status`: accuracy/readiness;
- `System Status`: data sources, auto processing, storage, security;
- `Key Metrics`: notes, projects, inbox, tasks, chunks.

Важно: метрики не должны быть фейковыми в production.

Правило:

- в prototype можно mock values;
- в Mini App все цифры должны идти из backend context.

### Main actions

Три действия на desktop:

- `Собрать отчет` -> `/draft/build`;
- `Добавить апдейт` или `Загрузить данные` -> открывает форму апдейта / импорт;
- `История отчетов` -> список drafts/final reports.

На mobile:

- главный CTA sticky bottom;
- вторичные действия в sheet/menu.

## 7. Workflow V2

V2 не должен возвращаться к “красивой, но непонятной витрине”.

Обязательный сценарий:

1. Пользователь видит dashboard.
2. Нажимает `Добавить апдейт` или `Собрать отчет`.
3. Если апдейтов нет — открывается форма добавления.
4. Если апдейты есть — собирается digest.
5. Пользователь видит preview и Telegram text.
6. Может скопировать, отправить себе, зафиксировать финал.

## 8. Модульная техническая структура

Рекомендуемые файлы:

- `src/delivery_reports/web/templates/index.html` — production dashboard.
- `src/delivery_reports/web/static/app.css` — shared tokens + current V1 styles.
- `src/delivery_reports/web/static/themes.css` — V2 theme tokens.
- `src/delivery_reports/web/static/v2-dashboard.css` — layout/cards/header.
- `src/delivery_reports/web/static/spiral.js` — canvas animation.
- `src/delivery_reports/web/static/app.js` — Telegram auth and shared UI behavior.

Prototype:

- `docs/prototypes/pm_digest_v2_preview.html` — standalone макет для согласования.

## 9. Canvas / Spiral animation

Требования:

- animation через `requestAnimationFrame`;
- pause/reduce при `prefers-reduced-motion: reduce`;
- particle count адаптируется:
  - desktop: 360-520;
  - tablet: 220-320;
  - mobile: 120-180;
- не блокировать ввод формы;
- не создавать motion sickness;
- CTA может на 1-2 секунды ускорять спираль при клике.

## 10. Адаптивность

### Desktop >= 1200px

- header full nav;
- hero cockpit;
- 3 action buttons;
- bottom status bar.

### Tablet 768-1199px

- cards уходят в 2 колонки;
- nav сокращается;
- spiral остается центральным, но ниже;
- bottom bar переносится в grid.

### Mobile <= 767px

- header: logo + plan + profile/theme;
- nav скрыть в menu;
- spiral уменьшить;
- cards идут одной колонкой;
- CTA sticky;
- report preview открывать отдельным блоком ниже или sheet;
- длинные тексты только в `textarea`/copy area.

## 11. Admin V2

Админка должна визуально соответствовать V2, но не смешиваться с PM dashboard.

Обязательные блоки:

- platform stats;
- users table;
- план пользователя;
- кнопки `PRO`, `TEAM`, `FREE`;
- events/audit;
- MRR estimate;
- conversion Free -> PRO;
- team panel для TEAM owner.

Безопасность:

- все admin actions доступны только `super_admin`;
- team dashboard доступен только owner/team admin;
- пользовательские данные изолированы по `telegram_user_id`.

## 12. Subscription V2

В dashboard:

- badge текущего плана;
- карточка тарифов;
- CTA `Открыть оплату в Telegram`;
- заблокированные PRO/TEAM фичи показывать как teaser, не как ошибку.

Тарифы:

- FREE: 3 проекта, 10 заметок/день, 7 дней истории;
- PRO: rich templates, weekly, export, AI editor, voice;
- TEAM: admin, monthly, shared templates, docs/presentations.

## 13. Acceptance Criteria

### Design

- визуал совпадает с направлением V2;
- есть 3 темы;
- активная тема сохраняется в `localStorage`;
- Telegram dark/light не ломает контраст;
- нет перегруза однотипным текстом;
- CTA визуально главный.

### UX

- пользователь понимает, что делать за 5 секунд;
- основные действия не спрятаны;
- длинный отчет не превращается в простыню;
- copy-ready Telegram text доступен отдельно.

### Tech

- V1 сохранен как rollback;
- V2 не ломает `pytest`;
- данные не фейковые в production;
- все формы работают через существующие routes;
- canvas не падает при hidden/zero-size container.

## 14. QA checklist

### Visual

- dark theme desktop;
- light lime desktop;
- wave blue desktop;
- mobile 390px;
- tablet 768px;
- long user name;
- zero notes;
- 20 notes / long report;
- no draft;
- draft exists;
- final exists.

### Functional

- add note;
- save and build;
- build draft;
- copy Telegram text;
- send draft to Telegram;
- finalize;
- send final;
- resolve inbox;
- add task;
- mark task done/waiting;
- switch theme;
- admin grant PRO/TEAM/FREE.

### Reliability

- no Telegram initData -> clear auth screen;
- no bot token -> clear Telegram send error;
- no projects -> default/empty state;
- no network fonts -> readable fallback;
- prefers-reduced-motion -> animation disabled/reduced.

## 15. План внедрения

### Step 1: согласование prototype

- открыть `docs/prototypes/pm_digest_v2_preview.html`;
- выбрать базовую тему;
- согласовать композицию и названия блоков.

### Step 2: split CSS

- вынести V2 tokens/themes в отдельный CSS;
- не удалять V1 styles.

### Step 3: production mapping

- подключить реальные `summary`, `user`, `tasks`, `draft`, `final_report`;
- убрать mock metrics.

### Step 4: frontend integration

- заменить dashboard shell;
- оставить формы V1 как panels/sheets;
- подключить theme switcher.

### Step 5: QA

- прогнать `pytest`;
- browser QA desktop/mobile;
- Telegram Mini App QA.
