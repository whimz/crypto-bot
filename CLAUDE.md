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

## Торговая логика
- Монеты: BTC, ETH, LTC
- Таймфреймы: 15 минут + 1 час
- Индикаторы: RSI(14), EMA(50), MACD(12,26,9)
- Трейлинг стоп-лосс: 7% от пика
- Максимум DCA: 3 подряд
- Максимум на символ: 40% депозита
- Глобальный стоп: -20% от начального депозита