# Crypto Bot — правила разработки

## Контекст
Торговый бот для Binance. Python + FastAPI + SQLite + React/Vite.
Этап: активная разработка на Testnet.

## Правила работы
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