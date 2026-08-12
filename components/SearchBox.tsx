import { useState } from 'react';

interface SearchBoxProps {
  placeholder: string;
  onSearch: (term: string) => void;
  className?: string;
}

export default function SearchBox({ placeholder, onSearch, className = '' }: SearchBoxProps) {
  const [value, setValue] = useState('');
  
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) {
      onSearch(value.trim());
    }
  };
  
  return (
    <form onSubmit={handleSubmit} className={`w-full ${className}`}
      style={{ 
        background: 'linear-gradient(135deg, #1e293b, #0f172a)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        boxShadow: '0 4px 6px rgba(0, 0, 0, 0.3)'
      }}>
      <div className="relative flex items-center">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={placeholder}
          className="w-full px-4 py-3 pl-12 bg-transparent text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-cyan-500 rounded-lg"
          style={{ fontSize: '16px' }}
        />
        <div className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/>
          </svg>
        </div>
        <button
          type="submit"
          className="ml-2 mr-2 px-6 py-2 bg-cyan-500 hover:bg-cyan-600 text-white font-medium rounded-lg transition-colors"
        >
          Search
        </button>
      </div>
    </form>
  );
}