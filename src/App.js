import React, { useState, useEffect, useMemo } from 'react';
import { supabase } from './supabaseClient';
import { 
  TrendingUp, 
  AlertTriangle, 
  ShieldAlert, 
  Package, 
  CheckCircle, 
  UserCheck, 
  Tag, 
  Filter, 
  RefreshCw, 
  MessageSquare,
  AlertCircle,
  ChevronDown,
  Star,
  DollarSign
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend
} from 'recharts';

// NLP Stopwords for word cloud
const STOPWORDS = new Set([
  'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', 'your', 'yours', 
  'he', 'him', 'his', 'she', 'her', 'it', 'its', 'they', 'them', 'their', 'theirs', 
  'what', 'which', 'who', 'whom', 'this', 'that', 'these', 'those', 'am', 'is', 'are', 
  'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 
  'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 
  'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 
  'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 
  'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 
  'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 
  'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 
  'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'd', 
  'll', 'm', 'o', 're', 've', 'y', 'ain', 'aren', 'couldn', 'didn', 'doesn', 'hadn', 
  'hasn', 'haven', 'isn', 'ma', 'mightn', 'mustn', 'needn', 'shan', 'shouldn', 'wasn', 
  'weren', 'won', 'wouldn', 'good', 'great', 'quality', 'product', 'bottle', 'buy', 
  'water', 'like', 'one', 'would', 'get', 'use', 'really', 'much', 'amazon', 'item', 
  'ordered', 'received', 'first'
]);

// Colors for charts
const RESPONSIBILITY_COLORS = {
  Customer: '#38bdf8', // Neon Blue
  Logistics: '#fbbf24', // Amber
  Manufacturing: '#f87171', // Red
  Marketing: '#a78bfa', // Purple
  Unknown: '#64748b' // Slate
};

const DISPOSITION_COLORS = {
  SELLABLE: '#10b981', // Emerald
  DEFECTIVE: '#ef4444', // Red
  CUSTOMER_DAMAGED: '#f97316', // Orange
  CARRIER_DAMAGED: '#eab308', // Yellow
  UNKNOWN: '#64748b'
};

function App() {
  // Loading & Data States
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [returnsData, setReturnsData] = useState([]);
  const [listingHealth, setListingHealth] = useState([]);
  const [listingReviews, setListingReviews] = useState([]);
  const [salesTraffic, setSalesTraffic] = useState([]);
  const [prevSalesTraffic, setPrevSalesTraffic] = useState([]);

  // Filter States
  const [selectedAccount, setSelectedAccount] = useState('All');
  const [selectedCountry, setSelectedCountry] = useState('All');
  const [timeRange, setTimeRange] = useState('90'); // days
  const [selectedCategory, setSelectedCategory] = useState('All');
  const [selectedSubCategory, setSelectedSubCategory] = useState('All');
  const [selectedProductSku, setSelectedProductSku] = useState(null);

  // Sorting States for Correlation Table
  const [sortField, setSortField] = useState('returnCost');
  const [sortDirection, setSortDirection] = useState('desc');

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };


  // Reset SKU filter when dropdowns change
  useEffect(() => {
    setSelectedProductSku(null);
  }, [selectedAccount, selectedCountry, timeRange, selectedCategory, selectedSubCategory]);

  // Reset subcategory when category changes
  useEffect(() => {
    setSelectedSubCategory('All');
  }, [selectedCategory]);

  // Fetch unique accounts/saddl_ids for filter dropdown
  const accounts = useMemo(() => {
    const list = new Set(returnsData.map(item => item.saddl_id).filter(Boolean));
    return ['All', ...Array.from(list)];
  }, [returnsData]);

  // Fetch unique categories
  const categories = useMemo(() => {
    const list = new Set(returnsData.map(item => item.mapped_category).filter(Boolean));
    return ['All', ...Array.from(list)];
  }, [returnsData]);

  // Fetch unique sub-categories
  const subCategories = useMemo(() => {
    let source = returnsData;
    if (selectedCategory !== 'All') {
      source = returnsData.filter(item => item.mapped_category === selectedCategory);
    }
    const list = new Set(source.map(item => item.mapped_sub_category).filter(Boolean));
    return ['All', ...Array.from(list)];
  }, [returnsData, selectedCategory]);

  // Mapping child ASIN to category details for sales filtering
  const asinToCategoryMap = useMemo(() => {
    const map = {};
    returnsData.forEach(item => {
      if (item.asin && item.mapped_category) {
        map[item.asin] = {
          category: item.mapped_category,
          subCategory: item.mapped_sub_category
        };
      }
    });
    return map;
  }, [returnsData]);

  // Helper to map client_id to Country
  const getCountryFromClientId = (clientId) => {
    if (!clientId) return null;
    const clean = clientId.toLowerCase();
    if (clean.includes('ksa')) return 'KSA';
    if (clean.includes('uae')) return 'UAE';
    if (clean === 's2c_test') return 'KSA';
    if (clean === 's2c_uae_test') return 'UAE';
    return null;
  };

  // Mapping ASIN to metadata (country, category)
  const asinMetadataMap = useMemo(() => {
    const map = {};
    returnsData.forEach(item => {
      if (item.asin) {
        map[item.asin] = {
          country: item.country,
          category: item.mapped_category,
          subCategory: item.mapped_sub_category
        };
      }
      if (item.parent_asin) {
        map[item.parent_asin] = {
          country: item.country,
          category: item.mapped_category,
          subCategory: item.mapped_sub_category
        };
      }
    });
    salesTraffic.forEach(item => {
      if (item.asin) {
        if (!map[item.asin]) {
          map[item.asin] = {
            country: item.country
          };
        }
      }
    });
    return map;
  }, [returnsData, salesTraffic]);

  // Fetch Data from Supabase
  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch unified returns from public view
      let allRetData = [];
      let from = 0;
      let step = 999;
      let hasMore = true;
      while (hasMore) {
        const { data, error } = await supabase
          .from('dashboard_returns')
          .select('*')
          .range(from, from + step);
        if (error) throw error;
        allRetData = [...allRetData, ...(data || [])];
        if (!data || data.length < step + 1) {
          hasMore = false;
        } else {
          from += step + 1;
        }
      }
      setReturnsData(allRetData);

      // 2. Fetch product listing health stats
      const { data: healthData, error: healthErr } = await supabase
        .from('product_listing_health')
        .select('*');
      if (healthErr) throw healthErr;
      setListingHealth(healthData || []);

      // 3. Fetch product public customer reviews
      const { data: reviewsData, error: reviewsErr } = await supabase
        .from('product_listing_reviews')
        .select('*');
      if (reviewsErr) throw reviewsErr;
      setListingReviews(reviewsData || []);

    } catch (err) {
      console.error("Error loading dashboard data:", err);
      setError(err.message || "Failed to load database data.");
    } finally {
      setLoading(false);
    }
  };

  const fetchSalesData = async (range) => {
    try {
      const { data, error } = await supabase.rpc('get_sales_by_range', { lookback_days: parseInt(range) });
      if (error) throw error;
      setSalesTraffic(data || []);

      const { data: doubleData, error: doubleErr } = await supabase.rpc('get_sales_by_range', { lookback_days: 2 * parseInt(range) });
      if (doubleErr) throw doubleErr;
      
      // Calculate previous sales traffic by subtracting current from double lookback
      const prevMap = {};
      (doubleData || []).forEach(item => {
        const key = `${item.asin}_${item.saddl_id}_${item.country}`;
        prevMap[key] = (prevMap[key] || 0) + (item.units_sold || 0);
      });
      (data || []).forEach(item => {
        const key = `${item.asin}_${item.saddl_id}_${item.country}`;
        if (prevMap[key] !== undefined) {
          prevMap[key] -= (item.units_sold || 0);
        }
      });
      
      const calculatedPrev = (doubleData || []).map(item => {
        const key = `${item.asin}_${item.saddl_id}_${item.country}`;
        return {
          ...item,
          units_sold: Math.max(0, prevMap[key] || 0)
        };
      });
      setPrevSalesTraffic(calculatedPrev);

    } catch (err) {
      console.error("Error fetching sales data:", err);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    fetchSalesData(timeRange);
  }, [timeRange]);


  // Filtered dataset selector
  const filteredReturns = useMemo(() => {
    const cutOffDate = new Date();
    cutOffDate.setDate(cutOffDate.getDate() - parseInt(timeRange));

    return returnsData.filter(item => {
      // Date filter
      const retDate = new Date(item.return_date);
      if (retDate < cutOffDate) return false;

      // Account filter
      if (selectedAccount !== 'All' && item.saddl_id !== selectedAccount) return false;

      // Country filter
      if (selectedCountry !== 'All' && item.country !== selectedCountry) return false;

      // Category filter
      if (selectedCategory !== 'All' && item.mapped_category !== selectedCategory) return false;

      // Sub-category filter
      if (selectedSubCategory !== 'All' && item.mapped_sub_category !== selectedSubCategory) return false;

      return true;
    });
  }, [returnsData, selectedAccount, selectedCountry, timeRange, selectedCategory, selectedSubCategory]);

  // Previous period returned dataset selector
  const previousReturns = useMemo(() => {
    const startPrev = new Date();
    startPrev.setDate(startPrev.getDate() - (2 * parseInt(timeRange)));
    
    const endPrev = new Date();
    endPrev.setDate(endPrev.getDate() - parseInt(timeRange));

    return returnsData.filter(item => {
      // Date filter
      const retDate = new Date(item.return_date);
      if (retDate < startPrev || retDate >= endPrev) return false;

      // Account filter
      if (selectedAccount !== 'All' && item.saddl_id !== selectedAccount) return false;

      // Country filter
      if (selectedCountry !== 'All' && item.country !== selectedCountry) return false;

      // Category filter
      if (selectedCategory !== 'All' && item.mapped_category !== selectedCategory) return false;

      // Sub-category filter
      if (selectedSubCategory !== 'All' && item.mapped_sub_category !== selectedSubCategory) return false;

      return true;
    });
  }, [returnsData, selectedAccount, selectedCountry, timeRange, selectedCategory, selectedSubCategory]);

  // Filtered sales dataset selector
  const filteredSales = useMemo(() => {
    return salesTraffic.filter(item => {
      // Account filter
      if (selectedAccount !== 'All' && item.saddl_id !== selectedAccount) return false;

      // Country filter
      if (selectedCountry !== 'All' && item.country !== selectedCountry) return false;

      // Category / Sub-category filter
      const catInfo = asinToCategoryMap[item.asin] || {};
      if (selectedCategory !== 'All' && catInfo.category !== selectedCategory) return false;
      if (selectedSubCategory !== 'All' && catInfo.subCategory !== selectedSubCategory) return false;

      return true;
    });
  }, [salesTraffic, selectedAccount, selectedCountry, asinToCategoryMap, selectedCategory, selectedSubCategory]);

  // Previous period filtered sales dataset selector
  const filteredPrevSales = useMemo(() => {
    return prevSalesTraffic.filter(item => {
      // Account filter
      if (selectedAccount !== 'All' && item.saddl_id !== selectedAccount) return false;

      // Country filter
      if (selectedCountry !== 'All' && item.country !== selectedCountry) return false;

      // Category / Sub-category filter
      const catInfo = asinToCategoryMap[item.asin] || {};
      if (selectedCategory !== 'All' && catInfo.category !== selectedCategory) return false;
      if (selectedSubCategory !== 'All' && catInfo.subCategory !== selectedSubCategory) return false;

      return true;
    });
  }, [prevSalesTraffic, selectedAccount, selectedCountry, asinToCategoryMap, selectedCategory, selectedSubCategory]);

  // Derived KPI calculations
  const kpis = useMemo(() => {
    const activeReturns = selectedProductSku 
      ? filteredReturns.filter(item => item.msku === selectedProductSku)
      : filteredReturns;
    
    const activeAsins = selectedProductSku
      ? new Set(returnsData.filter(ret => ret.msku === selectedProductSku).map(ret => ret.asin))
      : null;

    const activeSales = selectedProductSku
      ? filteredSales.filter(item => activeAsins.has(item.asin))
      : filteredSales;

    const totalUnits = activeReturns.reduce((sum, item) => sum + (item.quantity || 0), 0);
    const totalReturnCost = activeReturns.reduce((sum, item) => sum + (parseFloat(item.true_return_cost) || 0), 0);
    const sellableUnits = activeReturns.filter(item => item.disposition === 'SELLABLE')
                                          .reduce((sum, item) => sum + (item.quantity || 0), 0);
    const sellableRate = totalUnits > 0 ? (sellableUnits / totalUnits) * 100 : 0;

    // Global units sold & return rate
    const totalSalesUnits = activeSales.reduce((sum, item) => sum + (item.units_sold || 0), 0);
    const globalReturnRate = totalSalesUnits > 0 ? (totalUnits / totalSalesUnits) * 100 : 0;

    // Top return reason
    const reasonCounts = {};
    activeReturns.forEach(item => {
      const reason = item.reason_formatted || 'Unknown';
      reasonCounts[reason] = (reasonCounts[reason] || 0) + (item.quantity || 0);
    });
    const topReason = Object.keys(reasonCounts).reduce((a, b) => reasonCounts[a] > reasonCounts[b] ? a : b, 'None');

    // Top returned SKU
    const skuCounts = {};
    activeReturns.forEach(item => {
      const sku = item.msku || 'Unknown';
      skuCounts[sku] = (skuCounts[sku] || 0) + (item.quantity || 0);
    });
    const topSku = Object.keys(skuCounts).reduce((a, b) => skuCounts[a] > skuCounts[b] ? a : b, 'None');

    // Primary responsibility share
    const respCounts = {};
    activeReturns.forEach(item => {
      const resp = item.responsibility || 'Unknown';
      respCounts[resp] = (respCounts[resp] || 0) + (item.quantity || 0);
    });
    const topResp = Object.keys(respCounts).reduce((a, b) => respCounts[a] > respCounts[b] ? a : b, 'None');

    return {
      totalUnits,
      sellableRate,
      globalReturnRate,
      totalSalesUnits,
      topReason,
      topSku,
      topResp,
      respCounts,
      totalReturnCost
    };
  }, [filteredReturns, filteredSales, selectedProductSku, returnsData]);

  // Derived previous period KPI calculations
  const prevKpis = useMemo(() => {
    const activeReturns = selectedProductSku
      ? previousReturns.filter(item => item.msku === selectedProductSku)
      : previousReturns;

    const activeAsins = selectedProductSku
      ? new Set(returnsData.filter(ret => ret.msku === selectedProductSku).map(ret => ret.asin))
      : null;

    const activeSales = selectedProductSku
      ? filteredPrevSales.filter(item => activeAsins.has(item.asin))
      : filteredPrevSales;

    const totalUnits = activeReturns.reduce((sum, item) => sum + (item.quantity || 0), 0);
    const totalReturnCost = activeReturns.reduce((sum, item) => sum + (parseFloat(item.true_return_cost) || 0), 0);
    const sellableUnits = activeReturns.filter(item => item.disposition === 'SELLABLE')
                                          .reduce((sum, item) => sum + (item.quantity || 0), 0);
    const sellableRate = totalUnits > 0 ? (sellableUnits / totalUnits) * 100 : 0;

    const totalSalesUnits = activeSales.reduce((sum, item) => sum + (item.units_sold || 0), 0);
    const globalReturnRate = totalSalesUnits > 0 ? (totalUnits / totalSalesUnits) * 100 : 0;

    const uniqueAsins = selectedProductSku
      ? new Set(returnsData.filter(ret => ret.msku === selectedProductSku).map(ret => ret.asin).filter(Boolean))
      : new Set(previousReturns.map(item => item.parent_asin || item.asin).filter(Boolean));

    let reviewsCount = 0;
    uniqueAsins.forEach(asin => {
      const health = listingHealth.find(h => h.asin === asin) || {};
      reviewsCount += health.total_reviews ? parseInt(health.total_reviews) : 0;
    });

    return {
      totalUnits,
      sellableRate,
      globalReturnRate,
      totalSalesUnits,
      reviewsCount,
      totalReturnCost
    };
  }, [previousReturns, filteredPrevSales, listingHealth, selectedProductSku, returnsData]);

  // Aggregate daily return volumes and responsibilities
  const trendData = useMemo(() => {
    const aggregated = {};
    
    // 1. Get date range boundaries based on selected timeRange
    const today = new Date();
    const startDate = new Date();
    startDate.setDate(today.getDate() - parseInt(timeRange));
    
    // 2. Initialize all intermediate dates with 0 values
    const currentDate = new Date(startDate);
    while (currentDate <= today) {
      const dateKey = currentDate.toISOString().split('T')[0];
      aggregated[dateKey] = {
        date: dateKey,
        Returns: 0,
        Customer: 0,
        Logistics: 0,
        Manufacturing: 0,
        Marketing: 0,
        Unknown: 0
      };
      currentDate.setDate(currentDate.getDate() + 1);
    }
    
    // 3. Populate with actual return data
    filteredReturns.forEach(item => {
      const rawDateStr = item.return_date; // Sourced as string format
      if (!rawDateStr) return;
      
      const dateKey = rawDateStr.split('T')[0];
      if (!aggregated[dateKey]) {
        aggregated[dateKey] = {
          date: dateKey,
          Returns: 0,
          Customer: 0,
          Logistics: 0,
          Manufacturing: 0,
          Marketing: 0,
          Unknown: 0
        };
      }
      const qty = item.quantity || 0;
      aggregated[dateKey].Returns += qty;
      const resp = item.responsibility || 'Unknown';
      if (aggregated[dateKey][resp] !== undefined) {
        aggregated[dateKey][resp] += qty;
      } else {
        aggregated[dateKey].Unknown += qty;
      }
    });

    return Object.values(aggregated).sort((a, b) => a.date.localeCompare(b.date));
  }, [filteredReturns, timeRange]);

  // Aggregate outcomes (dispositions)
  const dispositionData = useMemo(() => {
    const counts = {};
    filteredReturns.forEach(item => {
      const disp = item.disposition || 'UNKNOWN';
      counts[disp] = (counts[disp] || 0) + (item.quantity || 0);
    });
    return Object.keys(counts).map(disp => ({
      name: disp.replace('_', ' ').title || disp,
      value: counts[disp],
      color: DISPOSITION_COLORS[disp] || DISPOSITION_COLORS.UNKNOWN
    }));
  }, [filteredReturns]);

  // Aggregate ranked reasons
  const topReasonsList = useMemo(() => {
    const counts = {};
    filteredReturns.forEach(item => {
      if (selectedProductSku && item.msku !== selectedProductSku) return;
      const reason = item.reason_formatted || 'Unknown';
      counts[reason] = (counts[reason] || 0) + (item.quantity || 0);
    });
    return Object.keys(counts)
      .map(reason => ({ name: reason, count: counts[reason] }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5);
  }, [filteredReturns, selectedProductSku]);

  // Correlation table logic: Returned products vs. listing stats
  const productsCorrelation = useMemo(() => {
    const productStats = {};
    filteredReturns.forEach(item => {
      const asin = item.asin;
      if (!asin) return;
      if (!productStats[asin]) {
        // Find rating details from health dataset (match parent_asin/asin with fallback client_id check)
        const health = listingHealth.find(h => h.asin === item.parent_asin && h.client_id === item.saddl_id) ||
                       listingHealth.find(h => h.asin === item.asin && h.client_id === item.saddl_id) ||
                       listingHealth.find(h => h.asin === item.parent_asin) ||
                       listingHealth.find(h => h.asin === item.asin) || {};
        productStats[asin] = {
          asin,
          parent_asin: item.parent_asin,
          msku: item.msku || 'Unknown SKU',
          title: item.title || 'Unknown Title',
          returnQty: 0,
          salesQty: 0,
          returnCost: 0,
          rating: health.star_rating ? parseFloat(health.star_rating) : null,
          reviewsCount: health.total_reviews ? parseInt(health.total_reviews) : 0,
          dispositions: {}
        };
      }
      productStats[asin].returnQty += (item.quantity || 0);
      productStats[asin].returnCost += (parseFloat(item.true_return_cost) || 0);
      const disp = item.disposition || 'UNKNOWN';
      productStats[asin].dispositions[disp] = (productStats[asin].dispositions[disp] || 0) + (item.quantity || 0);
    });

    // Populate sales quantity from filtered sales traffic
    filteredSales.forEach(sale => {
      const asin = sale.asin;
      if (asin && productStats[asin]) {
        productStats[asin].salesQty += (sale.units_sold || 0);
      }
    });

    // Calculate return rate
    Object.keys(productStats).forEach(asin => {
      const p = productStats[asin];
      p.returnRate = p.salesQty > 0 ? (p.returnQty / p.salesQty) * 100 : null;
    });

    // Dynamic sorting
    return Object.values(productStats).sort((a, b) => {
      let valA = a[sortField];
      let valB = b[sortField];

      // Custom ordering for risk badge
      if (sortField === 'risk') {
        const getRiskRank = (prod) => {
          const rQty = prod.returnQty;
          const rating = prod.rating;
          const rRate = prod.returnRate;
          const isHighRate = rRate !== null ? rRate >= 10.0 : rQty >= 20;
          const isModRate = rRate !== null ? (rRate >= 5.0 && rRate < 10.0) : (rQty >= 5 && rQty < 20);

          if (isHighRate && rating !== null && rating < 4.0) return 3;
          if (isModRate || (rating !== null && rating < 4.2)) return 2;
          return 1;
        };
        valA = getRiskRank(a);
        valB = getRiskRank(b);
      }

      // Handle null/undefined values by placing them at the bottom
      if (valA === valB) return 0;
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;

      if (typeof valA === 'string') {
        return sortDirection === 'asc' 
          ? valA.localeCompare(valB) 
          : valB.localeCompare(valA);
      } else {
        return sortDirection === 'asc'
          ? valA - valB
          : valB - valA;
      }
    });
  }, [filteredReturns, filteredSales, listingHealth, sortField, sortDirection]);

  // Filtered listing health for cumulative calculations
  const filteredListingHealth = useMemo(() => {
    return listingHealth.filter(item => {
      // Account filter
      if (selectedAccount !== 'All' && item.client_id !== selectedAccount) return false;

      // Country filter
      const country = getCountryFromClientId(item.client_id);
      if (selectedCountry !== 'All' && country && country !== selectedCountry) return false;

      const meta = asinMetadataMap[item.asin] || {};

      // Category filter
      if (selectedCategory !== 'All' && meta.category && meta.category !== selectedCategory) return false;

      // Sub-category filter
      if (selectedSubCategory !== 'All' && meta.subCategory && meta.subCategory !== selectedSubCategory) return false;

      // SKU filter if selected
      if (selectedProductSku) {
        const matchedAsins = new Set(
          returnsData
            .filter(ret => ret.msku === selectedProductSku)
            .map(ret => ret.asin)
        );
        if (!matchedAsins.has(item.asin)) return false;
      }

      // ONLY include active ASINs (which have active sales or returns in the returnsData/salesTraffic)
      const hasReturns = returnsData.some(r => r.asin === item.asin && r.saddl_id === item.client_id);
      const hasSales = salesTraffic.some(s => s.asin === item.asin && s.saddl_id === item.client_id);
      if (!hasReturns && !hasSales) return false;

      return true;
    });
  }, [listingHealth, selectedAccount, selectedCountry, selectedCategory, selectedSubCategory, asinMetadataMap, selectedProductSku, returnsData, salesTraffic]);

  // Total cumulative reviews count for all matched catalog products
  const totalReviewsMetric = useMemo(() => {
    return filteredListingHealth.reduce((sum, item) => sum + (item.total_reviews ? parseInt(item.total_reviews) : 0), 0);
  }, [filteredListingHealth]);

  // Compute a reliable star rating from percentage breakdown.
  // The scraped star_rating field is unreliable (can capture 1-star for popular listings
  // when the scraper hits a child ASIN page), but the pct breakdown is accurate.
  const computeRatingFromPct = (item) => {
    const p5 = parseFloat(item.five_star_pct) || 0;
    const p4 = parseFloat(item.four_star_pct) || 0;
    const p3 = parseFloat(item.three_star_pct) || 0;
    const p2 = parseFloat(item.two_star_pct) || 0;
    const p1 = parseFloat(item.one_star_pct) || 0;
    const total = p5 + p4 + p3 + p2 + p1;
    if (total < 50) return parseFloat(item.star_rating); // fallback when pct data is absent
    return (5 * p5 + 4 * p4 + 3 * p3 + 2 * p2 + 1 * p1) / total;
  };

  // Average star rating — grouped by parent ASIN, using percentage-computed rating per child.
  const averageStarRatingMetric = useMemo(() => {
    // Build asin → parent_asin map from returns data
    const asinToParent = {};
    returnsData.forEach(r => {
      if (r.asin && r.parent_asin) asinToParent[r.asin] = r.parent_asin;
    });

    // Group by parent ASIN; average all children's computed ratings per parent
    const parentMap = {};
    filteredListingHealth.forEach(item => {
      if (!item.asin) return;
      const rating = computeRatingFromPct(item);
      if (isNaN(rating)) return;
      const parent = asinToParent[item.asin] || item.asin;
      if (!parentMap[parent]) parentMap[parent] = { sum: 0, count: 0 };
      parentMap[parent].sum += rating;
      parentMap[parent].count += 1;
    });

    const entries = Object.values(parentMap);
    if (entries.length === 0) return 0;
    const totalSum = entries.reduce((acc, e) => acc + (e.sum / e.count), 0);
    return totalSum / entries.length;
  }, [filteredListingHealth, returnsData]);

  // Catalog average star rating of products in previous period (same pct-computed logic)
  const prevAverageStarRatingMetric = useMemo(() => {
    const prevAsins = new Set(previousReturns.map(item => item.asin || item.parent_asin).filter(Boolean));
    if (prevAsins.size === 0) return 0;

    const asinToParent = {};
    returnsData.forEach(r => {
      if (r.asin && r.parent_asin) asinToParent[r.asin] = r.parent_asin;
    });

    const parentMap = {};
    listingHealth
      .filter(item => prevAsins.has(item.asin))
      .forEach(item => {
        if (!item.asin) return;
        const rating = computeRatingFromPct(item);
        if (isNaN(rating)) return;
        const parent = asinToParent[item.asin] || item.asin;
        if (!parentMap[parent]) parentMap[parent] = { sum: 0, count: 0 };
        parentMap[parent].sum += rating;
        parentMap[parent].count += 1;
      });
    const entries = Object.values(parentMap);
    if (entries.length === 0) return 0;
    const totalSum = entries.reduce((acc, e) => acc + (e.sum / e.count), 0);
    return totalSum / entries.length;
  }, [previousReturns, listingHealth, returnsData]);

  // New reviews count in current lookback period
  const newReviewsCountCurrent = useMemo(() => {
    const cutOffDate = new Date();
    cutOffDate.setDate(cutOffDate.getDate() - parseInt(timeRange));
    
    return listingReviews.filter(rev => {
      // Date filter
      const revDate = new Date(rev.review_date);
      if (revDate < cutOffDate) return false;

      // Account filter
      if (selectedAccount !== 'All' && rev.client_id !== selectedAccount) return false;

      const meta = asinMetadataMap[rev.asin] || {};
      
      // Country filter
      const country = getCountryFromClientId(rev.client_id);
      if (selectedCountry !== 'All' && country && country !== selectedCountry) return false;

      // Category filter
      if (selectedCategory !== 'All' && meta.category && meta.category !== selectedCategory) return false;

      // Sub-category filter
      if (selectedSubCategory !== 'All' && meta.subCategory && meta.subCategory !== selectedSubCategory) return false;

      // SKU filter if selected
      if (selectedProductSku) {
        const matchedAsins = new Set(returnsData.filter(ret => ret.msku === selectedProductSku).map(ret => ret.asin));
        if (!matchedAsins.has(rev.asin)) return false;
      }

      return true;
    }).length;
  }, [listingReviews, timeRange, selectedAccount, selectedCountry, selectedCategory, selectedSubCategory, asinMetadataMap, selectedProductSku, returnsData]);

  // New reviews count in previous lookback period
  const newReviewsCountPrev = useMemo(() => {
    const startPrev = new Date();
    startPrev.setDate(startPrev.getDate() - (2 * parseInt(timeRange)));
    
    const endPrev = new Date();
    endPrev.setDate(endPrev.getDate() - parseInt(timeRange));

    return listingReviews.filter(rev => {
      // Date filter
      const revDate = new Date(rev.review_date);
      if (revDate < startPrev || revDate >= endPrev) return false;

      // Account filter
      if (selectedAccount !== 'All' && rev.client_id !== selectedAccount) return false;

      const meta = asinMetadataMap[rev.asin] || {};
      
      // Country filter
      const country = getCountryFromClientId(rev.client_id);
      if (selectedCountry !== 'All' && country && country !== selectedCountry) return false;

      // Category filter
      if (selectedCategory !== 'All' && meta.category && meta.category !== selectedCategory) return false;

      // Sub-category filter
      if (selectedSubCategory !== 'All' && meta.subCategory && meta.subCategory !== selectedSubCategory) return false;

      // SKU filter if selected
      if (selectedProductSku) {
        const matchedAsins = new Set(returnsData.filter(ret => ret.msku === selectedProductSku).map(ret => ret.asin));
        if (!matchedAsins.has(rev.asin)) return false;
      }

      return true;
    }).length;
  }, [listingReviews, timeRange, selectedAccount, selectedCountry, selectedCategory, selectedSubCategory, asinMetadataMap, selectedProductSku, returnsData]);

  // Average star rating by brand
  const brandRatings = useMemo(() => {
    const brands = {
      'S2C': { sum: 0, count: 0 },
      'Aurio': { sum: 0, count: 0 },
      'Oneshot': { sum: 0, count: 0 }
    };
    
    filteredListingHealth.forEach(item => {
      if (item.star_rating === null || item.star_rating === undefined) return;
      const rating = parseFloat(item.star_rating);
      if (isNaN(rating)) return;
      
      const clientId = item.client_id || 'unknown';
      let brandKey = 'S2C';
      if (clientId.toLowerCase().startsWith('aurio')) brandKey = 'Aurio';
      else if (clientId.toLowerCase().startsWith('oneshot')) brandKey = 'Oneshot';
      else if (clientId.toLowerCase().startsWith('s2c')) brandKey = 'S2C';
      else return; // skip other
      
      brands[brandKey].sum += rating;
      brands[brandKey].count += 1;
    });
    
    return Object.keys(brands).map(b => {
      const avg = brands[b].count > 0 ? (brands[b].sum / brands[b].count) : null;
      return {
        brand: b,
        avgRating: avg,
        count: brands[b].count
      };
    });
  }, [filteredListingHealth]);

  // Average rating by parent ASIN for client s2c_use_test
  const avgRatingByParent = useMemo(() => {
    const map = {};
    listingHealth.forEach(item => {
      if (item.client_id !== 's2c_uae_test') return;
      const parent = item.parent_asin || item.asin;
      if (!parent) return;
      const rating = parseFloat(item.star_rating);
      if (isNaN(rating)) return;
      if (!map[parent]) {
        map[parent] = { sum: 0, count: 0 };
      }
      map[parent].sum += rating;
      map[parent].count += 1;
    });
    return Object.entries(map).map(([parent, data]) => ({
      parent_asin: parent,
      avg_rating: data.count ? (data.sum / data.count).toFixed(2) : null,
      reviews: data.count
    }));
  }, [listingHealth]);

  // Sentiment Word Cloud (NLP Tokenizer)
  const wordCloud = useMemo(() => {
    const wordCounts = {};
    
    const selectedProduct = productsCorrelation.find(p => p.msku === selectedProductSku);
    const selectedParentAsin = selectedProduct ? (selectedProduct.parent_asin || selectedProduct.asin) : null;
    const activeParentAsins = new Set(filteredReturns.map(item => item.parent_asin).filter(Boolean));

    // 1. Parse comments from FBA returns in fact_returns
    filteredReturns.forEach(item => {
      if (selectedProductSku && item.msku !== selectedProductSku) return;
      
      const comment = item.customer_comments || '';
      const cleanText = comment.toLowerCase().replace(/[^\w\s]/g, ' ');
      cleanText.split(/\s+/).forEach(word => {
        if (word && word.length > 2 && !STOPWORDS.has(word)) {
          wordCounts[word] = (wordCounts[word] || 0) + 1;
        }
      });
    });

    // 2. Parse text reviews from active listing reviews in public table
    listingReviews.forEach(rev => {
      if (selectedProductSku) {
        if (rev.asin !== selectedParentAsin && rev.asin !== selectedProduct.asin) return;
      } else {
        const isMatch = activeParentAsins.has(rev.asin) || filteredReturns.some(item => item.asin === rev.asin);
        if (!isMatch) return;
      }
      const text = `${rev.title || ''} ${rev.review_text || ''}`.toLowerCase().replace(/[^\w\s]/g, ' ');
      text.split(/\s+/).forEach(word => {
        if (word && word.length > 2 && !STOPWORDS.has(word)) {
          wordCounts[word] = (wordCounts[word] || 0) + 1;
        }
      });
    });

    return Object.keys(wordCounts)
      .map(word => ({ text: word, value: wordCounts[word] }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 24); // Show top 24 words
  }, [filteredReturns, listingReviews, selectedProductSku, productsCorrelation]);

  // Combined Reviews & Return Comments feed
  const feedItems = useMemo(() => {
    const items = [];
    
    const selectedProduct = productsCorrelation.find(p => p.msku === selectedProductSku);
    const selectedParentAsin = selectedProduct ? (selectedProduct.parent_asin || selectedProduct.asin) : null;
    const activeParentAsins = new Set(filteredReturns.map(item => item.parent_asin).filter(Boolean));

    // Add return comments
    filteredReturns.forEach(item => {
      if (selectedProductSku && item.msku !== selectedProductSku) return;
      
      if (item.customer_comments) {
        items.push({
          date: item.return_date,
          type: 'Return Comment',
          sku: item.msku,
          rating: null,
          text: item.customer_comments,
          reason: item.reason_formatted || 'Unknown Reason'
        });
      }
    });

    // Add public listing reviews
    listingReviews.forEach(rev => {
      if (selectedProductSku) {
        if (rev.asin !== selectedParentAsin && rev.asin !== selectedProduct.asin) return;
      } else {
        const isMatch = activeParentAsins.has(rev.asin) || filteredReturns.some(item => item.asin === rev.asin);
        if (!isMatch) return;
      }
      items.push({
        date: rev.review_date,
        type: 'Public Review',
        sku: rev.asin, // ASIN reference (parent ASIN)
        rating: rev.rating,
        text: rev.review_text ? `${rev.title ? `"${rev.title}" - ` : ''}${rev.review_text}` : rev.title,
        reason: `${rev.sentiment} Sentiment`
      });
    });

    return items
      .sort((a, b) => new Date(b.date) - new Date(a.date))
      .slice(0, 15); // Show latest 15
  }, [filteredReturns, listingReviews, selectedProductSku, productsCorrelation]);


  // Dashboard Risk Index logic
  const getRiskBadge = (returnQty, rating, returnRate) => {
    // If we have a return rate, use it, else fallback to return qty
    const isHighRate = returnRate !== null ? returnRate >= 10.0 : returnQty >= 20;
    const isModRate = returnRate !== null ? (returnRate >= 5.0 && returnRate < 10.0) : (returnQty >= 5 && returnQty < 20);

    if (isHighRate && rating !== null && rating < 4.0) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-950 text-red-400 border border-red-800">
          Critical Risk
        </span>
      );
    } else if (isModRate || (rating !== null && rating < 4.2)) {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-950 text-orange-400 border border-orange-800">
          Moderate Warning
        </span>
      );
    } else {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950 text-emerald-400 border border-emerald-800">
          Healthy
        </span>
      );
    }
  };

  const renderComparison = (current, previous, isPercentage = false, invertColor = false, unit = null) => {
    if (previous === undefined || previous === null || previous === 0) {
      if (current === 0) return <span className="text-[10px] text-slate-500 mt-1">No change v last period</span>;
      return <span className="text-[10px] text-slate-500 mt-1">No previous data</span>;
    }
    
    let change = 0;
    if (isPercentage || unit) {
      change = current - previous;
    } else {
      change = ((current - previous) / previous) * 100;
    }
    
    const isPositive = change >= 0;
    
    // Determine decimal formatting based on unit
    let decimalPlaces = 1;
    if (unit === '★') decimalPlaces = 2;
    else if (unit === 'units' || unit === 'reviews') decimalPlaces = 0;
    
    const absChange = Math.abs(change).toFixed(decimalPlaces);
    
    let isGood = isPositive;
    if (invertColor) {
      isGood = !isPositive;
    }
    
    const colorClass = isGood ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold';
    const sign = isPositive ? '+' : '-';
    
    let suffix = '';
    if (isPercentage) {
      suffix = 'pp';
    } else if (unit) {
      suffix = ` ${unit}`;
    } else {
      suffix = '%';
    }
    
    return (
      <span className={`text-[10px] ${colorClass} flex items-center gap-0.5 mt-1`}>
        {sign}{absChange}{suffix} <span className="text-slate-500 font-normal">v last period</span>
      </span>
    );
  };

  const renderReviewsComparison = (currentNew, prevNew) => {
    const diff = currentNew - prevNew;
    const isPositive = diff >= 0;
    const absDiff = Math.abs(diff);
    const colorClass = isPositive ? 'text-emerald-400 font-semibold' : 'text-red-400 font-semibold';
    const sign = isPositive ? '+' : '-';
    
    return (
      <span className="text-[10px] text-slate-400 flex flex-col mt-1 font-medium leading-tight">
        <span>+{currentNew} new reviews</span>
        <span className={colorClass}>
          {sign}{absDiff} <span className="text-slate-500 font-normal">v last period</span>
        </span>
      </span>
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Header */}
      <header className="border-b border-slate-900 bg-slate-900/20 backdrop-blur-md sticky top-0 z-50 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-600/10 p-2.5 rounded-xl border border-indigo-500/30 shadow-indigo-500/10 shadow-inner">
            <ShieldAlert className="w-6 h-6 text-indigo-400" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight bg-gradient-to-r from-slate-100 via-indigo-200 to-indigo-400 bg-clip-text text-transparent">
              SADDL Returns Diagnostics
            </h1>
            <p className="text-xs text-slate-400">Root-cause analyzer & listing quality monitor</p>
          </div>
        </div>
        
        {/* Real-time sync trigger */}
        <div className="flex items-center gap-4">
          <button 
            onClick={fetchData} 
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-slate-800 bg-slate-900/40 hover:bg-slate-900 text-xs font-medium transition duration-200"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Refresh
          </button>
        </div>
      </header>

      <main className="flex-1 p-6 space-y-6 max-w-7xl mx-auto w-full">
        {/* Filters Panel */}
        <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-400 uppercase tracking-wider">
            <Filter className="w-4 h-4 text-indigo-400" />
            Filter View
          </div>
          <div className="flex flex-wrap items-center gap-4">
            {/* Account Selector */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 font-bold uppercase">Account</label>
              <div className="relative">
                <select
                  value={selectedAccount}
                  onChange={(e) => setSelectedAccount(e.target.value)}
                  className="appearance-none bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg block w-40 px-3 py-1.5 pr-8 focus:border-indigo-500 focus:ring-indigo-500 cursor-pointer"
                >
                  {accounts.map(acc => (
                    <option key={acc} value={acc}>{acc === 'All' ? 'All Accounts' : acc}</option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            </div>

            {/* Country Selector */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 font-bold uppercase">Country</label>
              <div className="relative">
                <select
                  value={selectedCountry}
                  onChange={(e) => setSelectedCountry(e.target.value)}
                  className="appearance-none bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg block w-32 px-3 py-1.5 pr-8 focus:border-indigo-500 focus:ring-indigo-500 cursor-pointer"
                >
                  <option value="All">All Regions</option>
                  <option value="UAE">UAE (AED)</option>
                  <option value="KSA">KSA (SAR)</option>
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            </div>

            {/* Category Selector */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 font-bold uppercase">Category</label>
              <div className="relative">
                <select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  className="appearance-none bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg block w-40 px-3 py-1.5 pr-8 focus:border-indigo-500 focus:ring-indigo-500 cursor-pointer"
                >
                  {categories.map(cat => (
                    <option key={cat} value={cat}>{cat === 'All' ? 'All Categories' : cat}</option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            </div>

            {/* Sub-category Selector */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 font-bold uppercase">Sub-category</label>
              <div className="relative">
                <select
                  value={selectedSubCategory}
                  onChange={(e) => setSelectedSubCategory(e.target.value)}
                  className="appearance-none bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg block w-40 px-3 py-1.5 pr-8 focus:border-indigo-500 focus:ring-indigo-500 cursor-pointer"
                >
                  {subCategories.map(sub => (
                    <option key={sub} value={sub}>{sub === 'All' ? 'All Sub-categories' : sub}</option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            </div>

            {/* Time selector */}
            <div className="flex flex-col gap-1">
              <label className="text-[10px] text-slate-500 font-bold uppercase">Lookback Window</label>
              <div className="relative">
                <select
                  value={timeRange}
                  onChange={(e) => setTimeRange(e.target.value)}
                  className="appearance-none bg-slate-950 border border-slate-800 text-slate-300 text-xs rounded-lg block w-36 px-3 py-1.5 pr-8 focus:border-indigo-500 focus:ring-indigo-500 cursor-pointer"
                >
                  <option value="7">Last 7 Days</option>
                  <option value="30">Last 30 Days</option>
                  <option value="90">Last 90 Days</option>
                  <option value="120">Last 120 Days</option>
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2.5 top-2.5 pointer-events-none" />
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="bg-red-950/40 border border-red-900 text-red-400 p-4 rounded-xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold">Database Error</h4>
              <p className="text-sm">{error}</p>
            </div>
          </div>
        )}

        {loading ? (
          <div className="h-[400px] flex flex-col items-center justify-center gap-4">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-indigo-500"></div>
            <p className="text-sm text-slate-400 font-medium">Aggregating returns ledger & listing health...</p>
          </div>
        ) : (
          <>
            {/* KPI Metrics Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-4">
              {/* Card 1: Total Returns */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-indigo-600/10 p-2.5 rounded-xl border border-indigo-500/20 shrink-0">
                    <Package className="w-4 h-4 text-indigo-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Total Returned</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-xl font-bold">{kpis.totalUnits} <span className="text-[10px] text-slate-500 font-normal">units</span></h3>
                  {renderComparison(kpis.totalUnits, prevKpis.totalUnits, false, true, 'units')}
                </div>
              </div>

              {/* Card 2: Return Rate */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-red-600/10 p-2.5 rounded-xl border border-red-500/20 shrink-0">
                    <TrendingUp className="w-4 h-4 text-red-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Return Rate</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-xl font-bold">{kpis.globalReturnRate.toFixed(1)}%</h3>
                  {renderComparison(kpis.globalReturnRate, prevKpis.globalReturnRate, true, true)}
                </div>
              </div>

              {/* Card 3: Restock Rate */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-emerald-600/10 p-2.5 rounded-xl border border-emerald-500/20 shrink-0">
                    <CheckCircle className="w-4 h-4 text-emerald-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Sellable Rate</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-xl font-bold">{kpis.sellableRate.toFixed(1)}%</h3>
                  {renderComparison(kpis.sellableRate, prevKpis.sellableRate, true, false)}
                </div>
              </div>

              {/* Card 4: Total Reviews */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-indigo-600/10 p-2.5 rounded-xl border border-indigo-500/20 shrink-0">
                    <MessageSquare className="w-4 h-4 text-indigo-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Total Reviews</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-xl font-bold">{totalReviewsMetric.toLocaleString()}</h3>
                  {renderReviewsComparison(newReviewsCountCurrent, newReviewsCountPrev)}
                </div>
              </div>

              {/* Card 5: Average Rating */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-amber-600/10 p-2.5 rounded-xl border border-amber-500/20 shrink-0">
                    <Star className="w-4 h-4 text-amber-400 fill-amber-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Average Rating</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-xl font-bold">
                    {averageStarRatingMetric > 0 ? (
                      <span className="text-amber-400 font-black">{averageStarRatingMetric.toFixed(2)} <span className="text-[10px] text-slate-500 font-normal">★</span></span>
                    ) : (
                      <span className="text-slate-500 text-xs font-normal">No data</span>
                    )}
                  </h3>
                  {renderComparison(averageStarRatingMetric, prevAverageStarRatingMetric, false, false, '★')}
                </div>
              </div>

              {/* Card 6: Top SKU */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-amber-600/10 p-2.5 rounded-xl border border-amber-500/20 shrink-0">
                    <Tag className="w-4 h-4 text-amber-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Top Returned SKU</p>
                </div>
                <div className="mt-2 truncate w-full">
                  <h3 className="text-sm font-bold truncate text-slate-200" title={kpis.topSku}>{kpis.topSku}</h3>
                  <span className="text-[10px] text-slate-500 mt-1 block">Most frequent returns</span>
                </div>
              </div>

              {/* Card 7: Return Financial Cost */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-red-600/10 p-2.5 rounded-xl border border-red-500/20 shrink-0">
                    <DollarSign className="w-4 h-4 text-red-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Return Cost</p>
                </div>
                <div className="mt-2 truncate w-full">
                  <h3 className="text-sm font-bold truncate text-red-400">
                    {selectedCountry === 'KSA' ? 'SAR' : selectedCountry === 'UAE' ? 'AED' : ''} {kpis.totalReturnCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
                  </h3>
                  {renderComparison(kpis.totalReturnCost, prevKpis.totalReturnCost, false, true)}
                </div>
              </div>

              {/* Card 8: Top Responsibility */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-4 flex flex-col justify-between hover:scale-[1.01] transition-transform duration-200 min-h-28">
                <div className="flex items-center gap-3">
                  <div className="bg-purple-600/10 p-2.5 rounded-xl border border-purple-500/20 shrink-0">
                    <UserCheck className="w-4 h-4 text-purple-400" />
                  </div>
                  <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Primary Cause</p>
                </div>
                <div className="mt-2">
                  <h3 className="text-base font-bold text-purple-300">{kpis.topResp}</h3>
                  <span className="text-[10px] text-slate-500 mt-1 block">Attributed department</span>
                </div>
              </div>
            </div>

                {/* Charts Section */}
            {/* Charts Section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Responsibility Attribution Trend (2/3 width) */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 lg:col-span-2 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-indigo-400" />
                    Attribution & Volume Trend
                  </h2>
                  <div className="text-[10px] text-slate-400 font-semibold bg-slate-800 px-2 py-1 rounded">Daily Aggregation</div>
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={trendData}>
                      <defs>
                        <linearGradient id="colorCustomer" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={RESPONSIBILITY_COLORS.Customer} stopOpacity={0.4}/>
                          <stop offset="95%" stopColor={RESPONSIBILITY_COLORS.Customer} stopOpacity={0.0}/>
                        </linearGradient>
                        <linearGradient id="colorLogistics" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={RESPONSIBILITY_COLORS.Logistics} stopOpacity={0.4}/>
                          <stop offset="95%" stopColor={RESPONSIBILITY_COLORS.Logistics} stopOpacity={0.0}/>
                        </linearGradient>
                        <linearGradient id="colorManufacturing" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={RESPONSIBILITY_COLORS.Manufacturing} stopOpacity={0.4}/>
                          <stop offset="95%" stopColor={RESPONSIBILITY_COLORS.Manufacturing} stopOpacity={0.0}/>
                        </linearGradient>
                        <linearGradient id="colorMarketing" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={RESPONSIBILITY_COLORS.Marketing} stopOpacity={0.4}/>
                          <stop offset="95%" stopColor={RESPONSIBILITY_COLORS.Marketing} stopOpacity={0.0}/>
                        </linearGradient>
                        <linearGradient id="colorUnknown" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor={RESPONSIBILITY_COLORS.Unknown} stopOpacity={0.4}/>
                          <stop offset="95%" stopColor={RESPONSIBILITY_COLORS.Unknown} stopOpacity={0.0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="date" stroke="#94a3b8" fontSize={11} />
                      <YAxis stroke="#94a3b8" fontSize={11} />
                      <Tooltip 
                        contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', color: '#f8fafc' }}
                        labelStyle={{ fontWeight: 'bold' }}
                      />
                      <Legend iconType="circle" wrapperStyle={{ fontSize: 11, paddingTop: 10 }} />
                      <Area type="monotone" dataKey="Customer" stroke={RESPONSIBILITY_COLORS.Customer} fillOpacity={1} fill="url(#colorCustomer)" stackId="1" />
                      <Area type="monotone" dataKey="Logistics" stroke={RESPONSIBILITY_COLORS.Logistics} fillOpacity={1} fill="url(#colorLogistics)" stackId="1" />
                      <Area type="monotone" dataKey="Marketing" stroke={RESPONSIBILITY_COLORS.Marketing} fillOpacity={1} fill="url(#colorMarketing)" stackId="1" />
                      <Area type="monotone" dataKey="Manufacturing" stroke={RESPONSIBILITY_COLORS.Manufacturing} fillOpacity={1} fill="url(#colorManufacturing)" stackId="1" />
                      <Area type="monotone" dataKey="Unknown" stroke={RESPONSIBILITY_COLORS.Unknown} fillOpacity={1} fill="url(#colorUnknown)" stackId="1" />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Outcomes & Brand Ratings Column (1/3 width) */}
              <div className="flex flex-col gap-6 lg:col-span-1">
                {/* Outcomes / Disposition Breakdown */}
                <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 space-y-4">
                  <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                    <Package className="w-4 h-4 text-emerald-400" />
                    Item Dispositions
                  </h2>
                  <div className="h-44 relative flex items-center justify-center">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={dispositionData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={65}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {dispositionData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                      </PieChart>
                    </ResponsiveContainer>
                    {/* Total indicator in donut hole */}
                    <div className="absolute text-center">
                      <p className="text-[9px] text-slate-400 font-bold uppercase">Restocked</p>
                      <p className="text-xl font-black text-emerald-400">{kpis.sellableRate.toFixed(0)}%</p>
                    </div>
                  </div>
                  {/* Custom Legend */}
                  <div className="grid grid-cols-2 gap-2 text-[10px]">
                    {dispositionData.map(item => (
                      <div key={item.name} className="flex items-center gap-1.5 text-slate-350">
                        <div className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: item.color }}></div>
                        <span className="truncate">{item.name}: {item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>

              </div>
            </div>

            {/* Middle Section: Top Reasons, Word Cloud & Product Correlation Matrix */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Product Health & Ratings Correlation Matrix */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 lg:col-span-2 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider">Product Quality & Listing Correlation</h2>
                  {selectedProductSku && (
                    <button 
                      onClick={() => setSelectedProductSku(null)}
                      className="text-xs bg-indigo-600/10 text-indigo-400 hover:bg-indigo-600/20 border border-indigo-500/25 px-2.5 py-1 rounded-lg transition duration-200"
                    >
                      Clear SKU Filter
                    </button>
                  )}
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-800 text-sm">
                    <thead>
                      <tr className="text-left text-xs font-semibold text-slate-400 uppercase tracking-wider select-none">
                        <th 
                          onClick={() => handleSort('msku')} 
                          className="py-3 px-2 cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center gap-1">
                            SKU
                            {sortField === 'msku' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('asin')} 
                          className="py-3 px-2 cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center gap-1">
                            ASIN
                            {sortField === 'asin' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('returnQty')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Returns
                            {sortField === 'returnQty' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('salesQty')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Units Sold
                            {sortField === 'salesQty' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('returnRate')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Return Rate
                            {sortField === 'returnRate' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('returnCost')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Return Cost
                            {sortField === 'returnCost' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('rating')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Listing Star
                            {sortField === 'rating' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('reviewsCount')} 
                          className="py-3 px-2 text-right cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-end gap-1">
                            Total Reviews
                            {sortField === 'reviewsCount' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                        <th 
                          onClick={() => handleSort('risk')} 
                          className="py-3 px-2 text-center cursor-pointer hover:text-slate-200 transition duration-150"
                        >
                          <span className="flex items-center justify-center gap-1">
                            Risk Badge
                            {sortField === 'risk' && (sortDirection === 'asc' ? ' ▲' : ' ▼')}
                          </span>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-900 text-slate-350">
                      {productsCorrelation.slice(0, 10).map(prod => {
                        const isSelected = selectedProductSku === prod.msku;
                        return (
                          <tr 
                            key={prod.asin} 
                            onClick={() => setSelectedProductSku(prev => prev === prod.msku ? null : prod.msku)}
                            className={`cursor-pointer transition duration-150 ${
                              isSelected 
                                ? 'bg-indigo-950/40 text-indigo-200 font-medium' 
                                : 'hover:bg-slate-900/20 text-slate-300'
                            }`}
                          >
                            <td className="py-3.5 px-2 font-semibold text-indigo-300 truncate max-w-40" title={prod.msku}>{prod.msku}</td>
                            <td className="py-3.5 px-2 font-mono text-xs">{prod.asin}</td>
                            <td className="py-3.5 px-2 text-right font-bold">{prod.returnQty}</td>
                            <td className="py-3.5 px-2 text-right font-medium text-slate-400">{prod.salesQty.toLocaleString()}</td>
                            <td className="py-3.5 px-2 text-right font-black text-indigo-300">
                              {prod.returnRate !== null ? (
                                `${prod.returnRate.toFixed(1)}%`
                              ) : (
                                <span className="text-slate-600 text-xs font-normal">N/A</span>
                              )}
                            </td>
                            <td className="py-3.5 px-2 text-right font-bold text-rose-400">
                              {prod.returnCost !== undefined ? (
                                `${selectedCountry === 'KSA' ? 'SAR' : selectedCountry === 'UAE' ? 'AED' : ''} ${prod.returnCost.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
                              ) : (
                                <span className="text-slate-600 text-xs font-normal">N/A</span>
                              )}
                            </td>
                            <td className="py-3.5 px-2 text-right">
                              {prod.rating !== null ? (
                                <span className="text-amber-400 font-bold">{prod.rating.toFixed(1)} <span className="text-[10px] text-slate-500">★</span></span>
                              ) : (
                                <span className="text-slate-500">No data</span>
                              )}
                            </td>
                            <td className="py-3.5 px-2 text-right">{prod.reviewsCount.toLocaleString()}</td>
                            <td className="py-3.5 px-2 text-center">{getRiskBadge(prod.returnQty, prod.rating, prod.returnRate)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Customer Comments Word Cloud / Pain Points */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 space-y-4">
                <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-indigo-400" />
                  Customer Pain Points
                  {selectedProductSku && (
                    <span className="text-[10px] bg-indigo-950/80 text-indigo-400 border border-indigo-800/50 px-2 py-0.5 rounded font-mono ml-auto shrink-0">
                      SKU: {selectedProductSku}
                    </span>
                  )}
                </h2>
                <p className="text-xs text-slate-400">Tokens extracted from return comments and negative reviews</p>
                <div className="flex flex-wrap gap-2.5 pt-2">
                  {wordCloud.length > 0 ? (
                    wordCloud.map((word, idx) => {
                      // Map size and color based on word count
                      const score = word.value;
                      let size = 'text-xs';
                      let color = 'bg-indigo-950/20 text-indigo-400 border-indigo-900';
                      if (score > 10) {
                        size = 'text-base font-extrabold';
                        color = 'bg-red-950/40 text-red-300 border-red-800';
                      } else if (score > 4) {
                        size = 'text-sm font-bold';
                        color = 'bg-orange-950/30 text-orange-400 border-orange-900';
                      }
                      
                      return (
                        <span 
                          key={word.text} 
                          className={`inline-flex items-center px-3 py-1 rounded-lg border uppercase tracking-wide cursor-default transition duration-200 hover:scale-105 ${size} ${color}`}
                          title={`Mentioned ${word.value} times`}
                        >
                          {word.text}
                        </span>
                      );
                    })
                  ) : (
                    <div className="w-full text-center py-10 text-xs text-slate-500">
                      No comments or reviews available yet to extract terms.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Bottom Row: Ranked Reasons list & Combined Customer comments feed */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Ranked Reasons */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 space-y-4">
                <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  Top Return Reasons
                  {selectedProductSku && (
                    <span className="text-[10px] bg-indigo-950/80 text-indigo-400 border border-indigo-800/50 px-2 py-0.5 rounded font-mono ml-auto shrink-0">
                      SKU: {selectedProductSku}
                    </span>
                  )}
                </h2>
                <div className="space-y-4">
                  {topReasonsList.map((reason, idx) => {
                    const activeTotal = selectedProductSku 
                      ? filteredReturns.filter(item => item.msku === selectedProductSku).reduce((sum, item) => sum + (item.quantity || 0), 0)
                      : kpis.totalUnits;
                    const percentage = activeTotal > 0 ? (reason.count / activeTotal) * 100 : 0;
                    return (
                      <div key={reason.name} className="space-y-1">
                        <div className="flex items-center justify-between text-xs font-semibold">
                          <span className="text-slate-300 truncate max-w-64">{reason.name}</span>
                          <span className="text-slate-400">{reason.count} units ({percentage.toFixed(0)}%)</span>
                        </div>
                        <div className="w-full bg-slate-950 h-2.5 rounded-full overflow-hidden border border-slate-850">
                          <div 
                            className="bg-indigo-500 h-full rounded-full" 
                            style={{ width: `${percentage}%` }}
                          ></div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Customer Reviews & Returns Feed (2/3 width) */}
              <div className="backdrop-blur-md bg-slate-900/30 border border-slate-800/80 shadow-lg rounded-2xl p-5 lg:col-span-2 space-y-4">
                <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-indigo-400" />
                  Combined Customer Feedback Feed
                  {selectedProductSku && (
                    <span className="text-[10px] bg-indigo-950/80 text-indigo-400 border border-indigo-800/50 px-2 py-0.5 rounded font-mono ml-auto shrink-0">
                      SKU: {selectedProductSku}
                    </span>
                  )}
                </h2>
                <div className="space-y-3.5 max-h-96 overflow-y-auto pr-2">
                  {feedItems.length > 0 ? (
                    feedItems.map((item, idx) => (
                      <div key={idx} className="p-3.5 rounded-xl border border-slate-850 bg-slate-950/40 hover:bg-slate-950/80 transition duration-150 space-y-1.5">
                        <div className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-2">
                            <span className={`px-2 py-0.5 rounded-md font-extrabold uppercase text-[9px] ${item.type === 'Public Review' ? 'bg-amber-950 text-amber-400 border border-amber-800' : 'bg-indigo-950 text-indigo-400 border border-indigo-800'}`}>
                              {item.type}
                            </span>
                            <span className="text-slate-400 font-bold font-mono">{item.sku}</span>
                          </div>
                          <span className="text-slate-500 font-medium">{new Date(item.date).toLocaleDateString()}</span>
                        </div>
                        <p className="text-sm font-medium text-slate-250 italic">"{item.text}"</p>
                        <div className="flex items-center gap-3 text-xs text-slate-500">
                          {item.rating && (
                            <span className="text-amber-400 font-bold">{item.rating} ★</span>
                          )}
                          <span className="font-semibold text-slate-400 uppercase tracking-wide">{item.reason}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-20 text-xs text-slate-500">
                      No matching reviews or comments found in the active selection.
                    </div>
                  )}
                </div>
              </div>
            </div>
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-900/10 px-6 py-4 flex items-center justify-between text-xs text-slate-500 mt-auto">
        <p>© 2026 SADDL LLC. All rights reserved.</p>
        <p className="font-medium">Data Lake Schema: returns.fact_returns</p>
      </footer>
    </div>
  );
}

export default App;
