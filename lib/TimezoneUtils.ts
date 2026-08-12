import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';

dayjs.extend(utc);
dayjs.extend(timezone);

export const formatLocalTime = (timestamp: number, timeZone: string = 'UTC'): string => {
  return dayjs(timestamp).tz(timeZone).format('h:mm A');
};

export const getTimezoneLabel = (timeZone: string): string => {
  const zones: Record<string, string> = {
    'UTC': 'UTC',
    'America/New_York': 'EST',
    'America/Los_Angeles': 'PST',
    'Europe/London': 'GMT',
    'Asia/Tokyo': 'JST',
  };
  return zones[timeZone] || timeZone;
};

export const isMarketHours = (hour: number, market: 'crypto' = 'crypto'): boolean => {
  // Crypto trades 24/7, but volume patterns exist
  return true; // Always true for crypto
};