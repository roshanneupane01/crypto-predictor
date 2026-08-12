import { useState, useEffect } from "react";
import Hero from "@/components/Hero";
import BuySellZone from "@/components/BuySellZone";
import StatsSection from "@/components/StatsSection";
import ChartSection from "@/components/ChartSection";
import TodayAtAGlance from "@/components/TodayAtAGlance";
import BestTimesSection from "@/components/BestTimesSection";
import DayOfWeekChart from "@/components/DayOfWeekChart";
import HoldingChart from "@/components/HoldingChart";
import ChatSection from "@/components/ChatSection";
import { useSearch } from "streamlit-search-box"; // or use custom search

// Mock data for demonstration
const mockPrice = 45231.50;
const mockChange24h = 2.45;
const mockLastUpdated = "March 17, 2026 14:30 UTC";
const mockEntryZone = [43200, 47000];
const mockSellZone = [47000, 50000];
const mockHoldDays = 12;
const mockRiskPct = 15.2;
const mockRewardPct = 22.8;
const mockLegRetPct = 12.4;

const Page = () => {
  const [searchTerm, setSearchTerm] = useState("");
  const [showChart, setShowChart] = useState(true);
  const [todayAtAGlance, setTodayAtAGlance] = useState(null);
  const [bestTimes, setBestTimes] = useState(null);
  const [dayOfWeekChart, setDayOfWeekChart] = useState(false);
  const [holdingChart, setHoldingChart] = useState(false);

  // Simulate data refresh
  useEffect(() => {
    const timer = setInterval(() => {
      setTodayAtAGlance(new Date());
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans">
      {/* Background Grid */}
      <div className="absolute inset-0 bg-[linear-gradient(to-right,#18181b_1px,transparent_1px),linear-gradient(to-bottom,#18181b_1px,transparent_1px)] bg-[size:40px_40px] opacity-30" />

      <div className="relative z-10 max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-4xl md:text-6xl font-bold text-slate-100 mb-2">📈 TradeSnapshot</h1>
          <p className="text-slate-400 text-sm">Patterns & trade timing for any Coinbase coin · times in your local time</p>
        </header>

        {/* Search Box */}
        <div className="mt-6 w-full max-w-2xl">
          <SearchBox 
            placeholder="Search cryptocurrency (BTC, ETH, SOL...)" 
            onSearch={(term) => console.log("Search:", term)}
          />
        </div>

        {/* Hero Section */}
        <Hero 
          selectedCoin="BTC"
          price={mockPrice}
          change24h={mockChange24h}
          lastUpdated={mockLastUpdated}
        />

        {/* Buy/Sell Zones */}
        <BuySellZone 
          entryZone={mockEntryZone}
          sellZone={mockSellZone}
          TZ_LABEL="Europe/Berlin"
        />

        {/* Stats Section */}
        <StatsSection 
          stats={{ entry: mockPrice, exit: 48000, holdDays: mockHoldDays, relativeStrength: 0.78 }}
          chartData={mockPriceData}
        />

        {/* Chart Section */}
        <ChartSection 
          data={mockPriceData}
          chartType="price_history"
        />

        {/* Today at A Glance */}
        <TodayAtAGlance 
          today={mockTodayAtAGlance}
          timezone={mockTimezone}
        />

        {/* Best Times */}
        <BestTimesSection 
          bestTimes={mockBestTimes}
          timezone={mockTimezone}
        />

        {/* Day of Week Chart */}
        <DayOfWeekChart 
          dayData={mockDayOfWeekData}
          chartTitle="Avg % / day"
        />

        {/* Holding Chart */}
        <HoldingChart 
          dailyChartData={mockHoldingChartData}
          title="Typical day"
        />

        {/* Chat Section */}
        <ChatSection 
          selectedCoin="BTC"
          initialProducts={["BTC", "ETH", "SOL", "ADA"]}
        />

        {/* Footer */}
        <footer className="absolute bottom-4 w-full text-center text-slate-500 text-xs bg-slate-900 bg-opacity-50 px-2 py-2 rounded-b-3xl">
          Built on Coinbase Pro API data since this coin listed. Patterns are historical tendencies, not guarantees — only invest what you can afford to lose.
        </footer>
      </div>
    </div>
  );
};

export default Page;