import Image from "next/image";
import Link from "next/link";
import { useState, useEffect } from "react";

export interface HeroCardProps {
  selectedCoin?: string;
  price?: number;
  change24h?: number;
  lastUpdated?: string;
}

export const Hero: React.FC<HeroCardProps> = ({ 
  selectedCoin, 
  price, 
  change24h, 
  lastUpdated 
}) => {
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowInfo(true), 5000);
    return () => clearTimeout(timer);
  }, [selectedCoin]);

  return (
    <div className="hero-card p-6 md:p-8 bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900 rounded-2xl border border-slate-700 min-h-[300px] flex flex-col justify-center">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-2xl font-bold text-slate-100">
          {selectedCoin || "Crypto Predictor"}
        </h2>
        <button
          onClick={() => setShowInfo(!showInfo)}
          className="text-sm text-slate-400 hover:text-slate-300 transition-colors"
        >
          {showInfo ? "Hide Details" : "Show Info"}
        </button>
      </div>

      {/* Price Display */}
      <div className="text-center mb-6">
        <Image
          src="/placeholder-crypto.svg"
          alt="Crypto asset"
          width={80}
          height={80}
          className="mx-auto mb-4"
        />
        <p className="text-4xl font-extrabold text-yellow-400">
          {price?.toLocaleString() || "--"}
        </p>
        <p className="text-slate-400 mt-1">USD</p>
      </div>

      {/* 24h Change */}
      {(change24h !== undefined && (
        <div className="flex justify-center mb-4">
          <span
            className={`text-lg font-medium ${
              change24h >= 0 ? "text-green-400" : "text-red-400"
            }`}
          >
            {change24h >= 0 ? "🟢" : "🔴"} {change24h.toFixed(2)}%
          </span>
        </div>
      ))}

      {/* Last Updated */}
      {lastUpdated && (
        <p className="text-center text-xs text-slate-500 mb-2">
          Last updated {lastUpdated}
        </p>
      )}

      {/* Info Tooltip */}
      {showInfo && (
        <div className="info-tooltip fixed top-20 right-8 bg-slate-800 p-4 rounded-xl border border-slate-700 max-w-xs shadow-lg z-50">
          <p className="text-sm text-slate-300">
            Real-time price data updates every 60 seconds. Price shown is the
            last traded price from Coinbase Pro API.
          </p>
        </div>
      )}
    </div>
  );
};

export default Hero;