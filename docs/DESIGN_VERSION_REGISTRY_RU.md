# Реестр дизайн-версий PM Digest

## V1 Current MVP

Статус: рабочая версия / rollback point.

Где находится:

- `src/delivery_reports/web/templates/index.html`
- `src/delivery_reports/web/static/app.css`
- `src/delivery_reports/web/static/app.js`

Что умеет:

- Telegram auth screen;
- быстрый апдейт;
- список сегодняшних заметок;
- задачи;
- inbox / resolve;
- сборка digest;
- preview + Telegram text;
- отправка себе в Telegram;
- финализация отчета;
- базовая админка и тарифы.

Когда пользователь говорит “верни V1”, откатываемся к этому UX-направлению: простой рабочий GRACE-flow без premium cockpit.

## V2 Target Prototype

Статус: дизайн-концепт на согласование.

Где находится:

- ТЗ: `docs/DESIGN_V2_PM_DIGEST_TZ_RU.md`
- HTML-макет: `docs/prototypes/pm_digest_v2_preview.html`

Что добавляет:

- premium dashboard;
- animated spiral / DNA core;
- темы `dark-lime`, `light-lime`, `wave-blue`;
- более сильные карточки метрик;
- top navigation;
- профиль / тариф / theme switcher;
- визуальный admin/subscription direction.

Когда пользователь говорит “делаем V2”, переносим prototype в production Mini App с сохранением всей логики V1.
