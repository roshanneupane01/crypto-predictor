import axios from 'axios';
import dayjs from 'dayjs';

export const fetchCoinbaseData = async (coinId: string) => {
  try {
    const response = await axios.get(`https://api.coinbase.com/v2/historical/prices?currency=USD&start=1622592000&end=1717180800&currency_pair=${coinId}USD`);
    const data = response.data.data.values.map((day) => ({
      timestamp: day.time * 1000,
      open: day.open,
      high: day.high,
      low: day.low,
      close: day.close,
      date: dayjs(day.time * 1000)
    }));
    return data.sort((a, b) => a.timestamp - b.timestamp);
  } catch (error) {
    console.error('Coinbase API error:', error.message);
    throw new Error('Failed to fetch Coinbase data');
  }
};

// Example usage:
// const coinData = await fetchCoinbaseData('BTC-USD');