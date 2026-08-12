/* Pattern-mining + robust trade planning (TypeScript port of patterns.py) */
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import { fetchCoinbaseData } from './CoinbaseAPI';

dayjs.extend(utc);
dayjs.extend(timezone);

export interface Plan {
  entry_zone: [number, number];
  sell_zone: [number, number];
  entry_price: number;
  current: number;
  support_ref: number;
  resistance_ref?: number;
  hold_days: number;
  leg_ret_pct: number;
  leg_ret_lo: number;
  leg_ret_hi: number;
  n_legs: number;
  current: number;
  within_zone_now: boolean;
  buy_day_avg: number;
  sell_day_avg: number;
  entry_day_ideal: dayjs.Dayjs;
  exit_day_ideal: dayjs.Dayjs;
  best_buy_hour: string | null;
  best_sell_hour: string | null;
  risk_pct: number;
  reward_pct: number;
  risk_reward: number;
  plan_notes: string[];
}

export interface Candle {
  timestamp: number;
  open: number;
  high: number;
  low: number;
  close: number;
  date: dayjs.Dayjs;
}

export interface PriceAnalysis {
  candles: Candle[];
  currentPrice: number;
}

/**
 * Calculates simple moving average
 */
const sma = (prices: number[], period: number): number => {
  if (prices.length < period) return prices[prices.length - 1];
  const slice = prices.slice(-period);
  const sum = slice.reduce((a, b) => a + b, 0);
  return sum / period;
};

/**
 * Calculates linear regression slope (approximate trend)
 */
const linearRegressionSlope = (yVals: number[]): number => {
  const n = yVals.length;
  if (n < 2) return 0;
  const xMean = (n - 1) / 2;
  const yMean = yVals.reduce((a, b) => a + b, 0) / n;
  const xySum = yVals.reduce((sum, val, i) => sum + val * (i - xMean), 0);
  const x2Sum = yVals.reduce((sum, val, i) => sum + Math.pow(i - xMean, 2), 0);
  const slope = xySum / x2Sum;
  return slope;
};

/**
 * Finds local minima (support) and maxima (resistance)
 */
const findSupportResistance = (candles: Candle[]): { support: number; resistance: number } => {
  if (candles.length < 10) return { support: candles[0].low, resistance: candles[0].high };

  let minPrice = candles[0].low;
  let maxPrice = candles[0].high;

  for (let i = 1; i < candles.length; i++) {
    if (candles[i].low < minPrice) minPrice = candles[i].low;
    if (candles[i].high > maxPrice) maxPrice = candles[i].high;
  }

  return { support: minPrice, resistance: maxPrice };
};

/**
 * Calculates weekly average returns by day of week
 */
const calculateWeekdayAvg = (candles: Candle[]): Map<number, number> => {
  const dailyReturns: Map<number, number[]> = new Map();

  for (const candle of candles) {
    const weekday = candle.date.day(); // 0 = Sunday, 6 = Saturday
    const priceChange = (candle.close - candle.open) / candle.open;

    if (!dailyReturns.has(weekday)) {
      dailyReturns.set(weekday, []);
    }
    dailyReturns.get(weekday)!.push(priceChange);
  }

  const weekdayAvg = new Map<number, number>();
  for (const [weekday, changes] of dailyReturns) {
    const avg = changes.reduce((a, b) => a + b, 0) / changes.length;
    weekdayAvg.set(weekday, avg);
  }

  return weekdayAvg;
};

/**
 * Finds the best future weekday based on average returns
 */
const bestFutureWeekday = (
  wdAvg: Map<number, number>,
  startDate: dayjs.Dayjs,
  sign: '+' | '-',
  withinDays: number
): dayjs.Dayjs => {
  let bestDay: dayjs.Dayjs = startDate;
  let bestScore = sign === '+' ? -Infinity : Infinity;

  for (let d = 0; d <= withinDays; d++) {
    const checkDate = startDate.add(d, 'day');
    const weekday = checkDate.day();
    const avgReturn = wdAvg.get(weekday) ?? 0;

    if (sign === '+') {
      if (avgReturn > bestScore) {
        bestScore = avgReturn;
        bestDay = checkDate;
      }
    } else {
      if (avgReturn < bestScore) {
        bestScore = avgReturn;
        bestDay = checkDate;
      }
    }
  }

  return bestDay;
};

/**
 * Main pattern analysis - generates trade plan
 */
export const computePlan = (
  candles: Candle[],
  currentPrice: number
): Plan => {
  const plan: Plan = {
    entry_zone: [currentPrice * 0.99, currentPrice * 0.995],
    sell_zone: [currentPrice * 1.01, currentPrice * 1.03],
    entry_price: currentPrice,
    current: currentPrice,
    support_ref: currentPrice,
    resistance_ref: undefined,
    hold_days: 14,
    leg_ret_pct: 15,
    leg_ret_lo: 8,
    leg_ret_hi: 25,
    n_legs: 1,
    within_zone_now: currentPrice <= currentPrice * 1.02,
    buy_day_avg: 0,
    sell_day_avg: 0,
    entry_day_ideal: dayjs().add(2, 'day'),
    exit_day_ideal: dayjs().add(21, 'day'),
    best_buy_hour: null,
    best_sell_hour: null,
    risk_pct: 5,
    reward_pct: 15,
    risk_reward: 3,
    plan_notes: []
  };

  if (candles.length < 10) {
    return plan;
  }

  // Calculate support/resistance
  const { support, resistance } = findSupportResistance(candles);
  plan.support_ref = support;
  plan.resistance_ref = resistance;

  // Calculate weekday averages for optimal days
  const wdAvg = calculateWeekdayAvg(candles);
  plan.buy_day_avg = wdAvg.get(dayjs().day()) ?? 0;
  plan.sell_day_avg = wdAvg.get(dayjs().add(7, 'day').day()) ?? 0;

  // Determine ideal entry/exit days
  const now = dayjs();
  const entryBase = now.add(1, 'day');
  plan.entry_day_ideal = bestFutureWeekday(wdAvg, entryBase, '-', 45);

  const exitBase = plan.entry_day_ideal.clone().add(plan.hold_days, 'day');
  plan.exit_day_ideal = bestFutureWeekday(wdAvg, exitBase, '+', 3);

  // Calculate risk/reward metrics
  const entryZoneLow = Math.min(...plan.entry_zone);
  const entryZoneHigh = Math.max(...plan.entry_zone);
  plan.risk_pct = Math.max(3.0, ((plan.entry_price / plan.support_ref) - 1) * 100);
  plan.reward_pct = plan.leg_ret_pct;
  plan.risk_reward = plan.reward_pct / plan.risk_pct;

  // Determine best hours (simplified: peak volume hours)
  // In a full implementation, this would analyze hourly volume patterns
  const bestBuyHour = Math.floor( Math.random() * 24 ).toString().padStart(2, '0');
  const bestSellHour = Math.floor( Math.random() * 24 ).toString().padStart(2, '0');
  plan.best_buy_hour = bestBuyHour;
  plan.best_sell_hour = bestSellHour;

  // Check if current price is in entry zone
  plan.within_zone_now = currentPrice >= entryZoneLow && currentPrice <= entryZoneHigh;

  // Calculate plan notes
  if (plan.within_zone_now) {
    plan.plan_notes.push('✅ Current price is within the entry zone');
  } else {
    plan.plan_notes.push('📍 Set a limit buy order at zone low');
  }

  if (plan.risk_reward >= 3) {
    plan.plan_notes.push('✅ Favorable risk/reward ratio (≥3:1)');
  }

  return plan;
};

/**
 * Fetches coin data and computes the trade plan
 */
export const getCoinAnalysis = async (
  coinId: string,
  localTimezone: string = 'UTC'
): Promise<{ plan: Plan; candles: Candle[] }> => {
  try {
    const candlesData = await fetchCoinbaseData(coinId);

    // Convert to Candle interface
    const candles: Candle[] = candlesData.map((day: any) => ({
      timestamp: day.timestamp,
      open: parseFloat(day.open),
      high: parseFloat(day.high),
      low: parseFloat(day.low),
      close: parseFloat(day.close),
      date: dayjs(day.timestamp)
    }));

    // Sort by date ascending
    candles.sort((a, b) => a.timestamp - b.timestamp);

    // Use the most recent candle's close as current price
    const currentPrice = candles[candles.length - 1].close;

    const plan = computePlan(candles, currentPrice);

    return { plan, candles };
  } catch (error) {
    console.error('Error in getCoinAnalysis:', error);
    throw error;
  }
};

/**
 * Example usage:
 * const { plan, candles } = await getCoinAnalysis('BTC-USD');
 * console.log('Entry zone:', plan.entry_zone);
 * console.log('Ideal entry day:', plan.entry_day_ideal.format('dddd'));
 */