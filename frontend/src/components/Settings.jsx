import { useCallback, useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { getSettings, updateSettings } from "../api.js";
import { showToast } from "../toastBus.js";
import Tooltip from "./Tooltip.jsx";

const FIELDS = [
  {
    key: "rsi_oversold",
    label: "RSI Oversold",
    step: 1,
    what: "Уровень RSI ниже которого бот считает актив перепроданным и покупает",
    optimal: "30-35 — классический уровень перепроданности",
    risk: "слишком низкое (10-20) — бот почти никогда не купит. Слишком высокое (50+) — будет покупать постоянно и потратит депозит",
  },
  {
    key: "rsi_overbought",
    label: "RSI Overbought",
    step: 1,
    what: "Уровень RSI выше которого бот считает актив перекупленным и продаёт",
    optimal: "65-70 — классический уровень перекупленности",
    risk: "слишком высокое (90+) — бот почти никогда не продаст. Слишком низкое (50-) — продаёт сразу после покупки",
  },
  {
    key: "confidence_threshold",
    label: "Confidence Threshold",
    step: 1,
    what: "Минимальная уверенность сигнала (0-100) при которой бот действует",
    optimal: "65-75 — баланс между частотой сделок и качеством",
    risk: "низкое (30-40) — много ложных сделок. Высокое (90+) — бот почти никогда не торгует",
  },
  {
    key: "trailing_stop_pct",
    label: "Trailing Stop %",
    step: 0.01,
    isFraction: true,
    what: "Процент падения от максимальной цены после которого бот продаёт",
    optimal: "5-10% — достаточно для нормальных коррекций",
    risk: "маленький (1-2%) — продаст при малейшей коррекции. Большой (20%+) — держит убыточную позицию слишком долго",
  },
  {
    key: "max_allocation_pct",
    label: "Max Allocation %",
    step: 0.01,
    isFraction: true,
    what: "Максимальная доля депозита которую можно вложить в одну монету",
    optimal: "30-40% — диверсификация между монетами",
    risk: "100% — все деньги в одной монете. Меньше 10% — комиссии съедят прибыль",
  },
  {
    key: "max_dca_count",
    label: "Max DCA Count",
    step: 1,
    what: "Максимальное количество усреднений подряд без продажи",
    optimal: "3-5 — достаточно для усреднения без риска",
    risk: "высокое (10+) — вложит весь депозит в падающий актив. Низкое (1) — мало возможностей для усреднения",
  },
  {
    key: "global_stop_pct",
    label: "Global Stop %",
    step: 0.01,
    isFraction: true,
    what: "При падении депозита на этот процент — бот останавливает покупки",
    optimal: "15-25% — защита без ложных срабатываний",
    risk: "высокое (50%+) — слишком поздняя защита. Низкое (5%) — бот остановится при малейших потерях",
  },
  {
    key: "cycle_minutes",
    label: "Cycle Minutes",
    step: 1,
    what: "Как часто бот анализирует рынок и принимает решения",
    optimal: "15 минут — баланс между скоростью и нагрузкой",
    risk: "частый (1-2 мин) — риск rate limit Binance. Редкий (60+ мин) — пропустит быстрые движения",
  },
];

const TELEGRAM_FIELDS = [
  { key: "notify_trades", label: "Сделки (BUY/SELL)" },
  { key: "notify_errors", label: "Ошибки бота" },
  { key: "notify_stops", label: "Старт/стоп бота" },
  { key: "notify_inactive", label: "Неактивность > 20 минут" },
];

const DIAGNOSTICS_FIELDS = [
  { key: "debug_logging", label: "Подробный лог HOLD-циклов" },
];

const ADVANCED_FIELDS = [
  {
    key: "require_ema_trend",
    label: "Require EMA trend filter",
    what: "Требует совпадения цены с трендом EMA50 на обоих таймфреймах (15м и 1ч) для BUY/SELL, в дополнение к условию RSI",
    risk: "Когда выключено, бот может покупать/продавать против общего тренда — используйте только для тестирования, не оставляйте выключенным в постоянной работе",
  },
];

// `form` always holds display values (fractions shown as whole percentages); conversion
// to/from the API's fraction representation happens only at the load/save boundary.
function toDisplayForm(field, value) {
  return field.isFraction ? Number(value) * 100 : value;
}

function toApiValue(field, value) {
  return field.isFraction ? Number(value) / 100 : Number(value);
}

function settingsToForm(settings) {
  const form = {};
  for (const field of FIELDS) form[field.key] = toDisplayForm(field, settings[field.key]);
  for (const field of TELEGRAM_FIELDS) form[field.key] = Boolean(settings[field.key]);
  for (const field of DIAGNOSTICS_FIELDS) form[field.key] = Boolean(settings[field.key]);
  for (const field of ADVANCED_FIELDS) form[field.key] = Boolean(settings[field.key]);
  return form;
}

export default function Settings() {
  const [settings, setSettings] = useState(null);
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getSettings();
      setSettings(data);
      setForm(settingsToForm(data));
    } catch (err) {
      showToast({
        title: "Failed to load settings",
        description: err.message,
        requestId: err.requestId,
        retry: load,
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleFieldChange = (key, value) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updates = {};
      for (const field of FIELDS) {
        updates[field.key] = toApiValue(field, form[field.key]);
      }
      for (const field of TELEGRAM_FIELDS) {
        updates[field.key] = Boolean(form[field.key]);
      }
      for (const field of DIAGNOSTICS_FIELDS) {
        updates[field.key] = Boolean(form[field.key]);
      }
      for (const field of ADVANCED_FIELDS) {
        updates[field.key] = Boolean(form[field.key]);
      }
      const saved = await updateSettings(updates);
      setSettings(saved);
      setForm(settingsToForm(saved));
      showToast({ title: "Settings saved", description: "Strategy parameters updated successfully." });
    } catch (err) {
      showToast({
        title: "Failed to save settings",
        description: err.message,
        requestId: err.requestId,
        retry: handleSave,
      });
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <div className="card">
        <h2>Settings</h2>
        <div className="empty-state">Loading...</div>
      </div>
    );
  }

  return (
    <div className="card">
      <h2>Settings</h2>
      <div className="settings-grid">
        {FIELDS.map((field) => (
          <div className="settings-field" key={field.key}>
            <label>
              {field.label}
              <Tooltip what={field.what} optimal={field.optimal} risk={field.risk} />
            </label>
            <input
              type="number"
              step={field.step}
              value={form[field.key] ?? ""}
              onChange={(e) => handleFieldChange(field.key, e.target.value)}
            />
          </div>
        ))}
      </div>

      <h3 className="settings-subheading">Telegram Notifications</h3>
      <div className="settings-toggle-grid">
        {TELEGRAM_FIELDS.map((field) => (
          <label className="settings-toggle" key={field.key}>
            <input
              type="checkbox"
              checked={Boolean(form[field.key])}
              onChange={(e) => handleFieldChange(field.key, e.target.checked)}
            />
            {form[field.key] ? "🟢" : "⚪"} {field.label}
          </label>
        ))}
      </div>

      <h3 className="settings-subheading">Diagnostics</h3>
      <div className="settings-toggle-grid">
        {DIAGNOSTICS_FIELDS.map((field) => (
          <label className="settings-toggle" key={field.key}>
            <input
              type="checkbox"
              checked={Boolean(form[field.key])}
              onChange={(e) => handleFieldChange(field.key, e.target.checked)}
            />
            {form[field.key] ? "🟢" : "⚪"} {field.label}
          </label>
        ))}
      </div>

      <div className="settings-advanced">
        <h3 className="settings-advanced-heading">
          <AlertTriangle size={14} />
          Advanced / Testing
        </h3>
        <div className="settings-toggle-grid">
          {ADVANCED_FIELDS.map((field) => (
            <div className="settings-toggle-row" key={field.key}>
              <label className="settings-toggle">
                <input
                  type="checkbox"
                  checked={Boolean(form[field.key])}
                  onChange={(e) => handleFieldChange(field.key, e.target.checked)}
                />
                {form[field.key] ? "🟢" : "⚪"} {field.label}
              </label>
              <Tooltip what={field.what} risk={field.risk} />
            </div>
          ))}
        </div>
      </div>

      <button className="primary settings-save" onClick={handleSave} disabled={saving}>
        {saving ? "Saving..." : "Save"}
      </button>
    </div>
  );
}
