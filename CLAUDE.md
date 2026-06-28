# Crypto Bot — правила разработки

## Контекст
Торговый бот для Binance. Python + FastAPI + SQLite + React/Vite.
Этап: активная разработка на Testnet.

## Правила работы
- Задание подробно анализируется до старта
- Все уточняющие вопросы — только в начале задачи
- После старта — действуй автономно без лишних вопросов
- Перед реализацией — анализ существующего кода
- Не ломай то что уже работает

## Стек
- Backend: Python 3.14 + FastAPI + SQLite
- Frontend: React + Vite
- Торговля: Binance API (сейчас Testnet)
- Уведомления: Telegram Bot

## Структура
- backend/data/binance.py — клиент Binance API
- backend/analysis/indicators.py — RSI, EMA, MACD
- backend/trading/signals.py — торговые сигналы
- backend/trading/risk.py — риск-менеджмент
- backend/trading/executor.py — исполнение ордеров
- backend/db/storage.py — история сделок SQLite
- backend/notifications/telegram.py — алерты
- backend/scheduler.py — цикл бота (run_cycle, start/stop/shutdown_bot)
- backend/api.py — FastAPI роуты и middleware
- backend/main.py — точка входа (uvicorn)

## Торговая логика
- Монеты: BTC, ETH, LTC
- Таймфреймы: 15 минут + 1 час
- Индикаторы: RSI(14), EMA(50), MACD(12,26,9)
- Трейлинг стоп-лосс: 7% от пика
- Максимум DCA: 3 подряд
- Максимум на символ: 40% депозита
- Глобальный стоп: -20% от начального депозита

## Принципы кода
- Single Responsibility: каждый модуль делает одно дело,
  файл > 300 строк — сигнал к разбиению
- Типизация везде: аннотации типов на всех функциях
- Fail fast: валидация входных данных в начале функции
- Конфигурация в config.py: никаких магических чисел в коде
- Ошибки не теряются: каждый except логирует и уведомляет
- Логирование решений: каждое действие бота объяснено в логе
- Комментарии объясняют ПОЧЕМУ, не ЧТО
- DRY: дублирование 2+ раза → выносить в функцию
- Функция делает одно действие, оркестрация в scheduler
- Тесты для: риск-менеджмента, индикаторов, сигналов

## UI Error Standard
Все ошибки через Toast компонент (нижний правый угол):
- Что сломалось (заголовок)
- Почему (описание ошибки)
- Что дальше (retry / dismiss)
- requestId + кнопка копирования
Никаких alert() или console.error() в UI.
Все ошибки сети, 4xx, 5xx — только через Toast.

## Статус проекта
Обновлять эту секцию после каждого завершённого спринта.

### Что реализовано
Backend:
- binance.py — клиент Binance API + Testnet
- indicators.py — RSI(14), EMA(50), MACD(12,26,9)
- signals.py — логика BUY/SELL/HOLD (2 таймфрейма)
- risk.py — трейлинг стоп 7%, DCA, аллокация
- executor.py — исполнение ордеров
- storage.py — SQLite + миграции
- scheduler.py — цикл каждые 15 минут
- api.py — REST API + JWT авторизация
- auth.py — логин/токены
- settings.py — настройки в runtime
- telegram.py — уведомления + команды

Frontend:
- Login.jsx — авторизация
- Header.jsx — статус, Start/Stop, аккаунт, Trade settings в дропдауне
- Portfolio.jsx — депозит, просадка, Set Deposit
- Positions.jsx — позиции + PnL
- Chart.jsx — свечной график + RSI
- DepositChart.jsx — график депозита во времени
- ActivityLog.jsx — лог решений бота + фильтры, пагинация 25 + infinite scroll
- Trades.jsx — история сделок + экспорт CSV
- SettingsDrawer.jsx — настройки стратегии в slide-over панели (вызов из Header)
- Toast.jsx — UI уведомления об ошибках
- FadeInSection.jsx — fade-in анимация карточек по IntersectionObserver
- Tailwind CSS — подключён, токены темы/breakpoints в tailwind.config.js
- Layout: парные карточки 50%/50% в ряд, max-width: min(85vw, 1600px)

Инфраструктура:
- Railway Volume — персистентная БД
- GitHub Actions — автодеплой
- CLAUDE.md — правила для Claude Code
- 42 теста — покрытие критической логики
- backup.py — ежедневный бэкап SQLite в Cloudflare R2 (03:00 UTC, Telegram-алерт при ошибке)

### Деплой
Backend:  https://crypto-bot-production-3c5c.up.railway.app
Frontend: https://crypto-bot-ebg.pages.dev
БД:       Railway Volume /app/backend/data

### TODO
TODO — это не команды для работы, а идеи на будущее, реализуются по мере возможности.

Функционал:
- Sync Balance с Binance (реальный баланс USDT)
- Пресеты стратегий:
  - Conservative (RSI 30/70, confidence 75)
  - Moderate (RSI 35/65, confidence 70) ← текущая
  - Aggressive (RSI 40/60, confidence 60)
- Адаптивная стратегия — Claude анализирует рынок и выбирает оптимальный пресет автоматически
- WebSocket мониторинг стоп-лосса в реальном времени
- Bollinger Bands как альтернативный индикатор

Будущее:
- Фьючерсы (SHORT стратегия, плечо ×2), учитывать фандинг рейт при решениях
- Мультипользовательская система
- Поддержка большего количества монет
- Backtesting на исторических данных