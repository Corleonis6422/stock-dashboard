#!/usr/bin/env python3
"""
Quant Action Gauge Backtest & Historical Simulation Engine
Simulates and validates whether the Quant Action Gauge produces profitable trading decisions
over 3-day, 5-day (1-week), 10-day (2-week), and 20-day (1-month) holding periods.
Also performs weight sensitivity analysis (Z-Score vs Volume-Price vs Smart Money).
"""

import sys
import ssl
import json
import math
import random
import urllib.request
from datetime import datetime

# Ensure utf-8 encoding on Windows console
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def fetch_history(ticker, range_val="1y"):
    """Fetch historical OHLCV data from Binance (for crypto) or Yahoo Finance API."""
    ctx = ssl._create_unverified_context()
    if ticker.upper() in ['BTC-USD', 'BTC', 'BTCUSDT', 'ETH-USD', 'ETH', 'SOL-USD', 'SOL']:
        symbol = 'BTCUSDT' if ticker.upper().startswith('BTC') else ticker.upper().replace('-USD', 'USDT')
        try:
            b_url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=365"
            b_req = urllib.request.Request(b_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(b_req, context=ctx, timeout=10) as resp:
                klines = json.loads(resp.read().decode('utf-8'))
                valid_days = []
                for k in klines:
                    ts = int(k[0] // 1000)
                    valid_days.append({
                        'timestamp': ts,
                        'date': datetime.fromtimestamp(ts).strftime('%Y-%m-%d'),
                        'open': float(k[1]),
                        'high': float(k[2]),
                        'low': float(k[3]),
                        'close': float(k[4]),
                        'volume': float(k[7])
                    })
                if len(valid_days) > 30:
                    return valid_days
        except Exception as e:
            print(f"Binance fetch failed for {ticker}, trying Yahoo: {e}")

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range={range_val}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
        result = data['chart']['result'][0]
        timestamps = result.get('timestamp', [])
        quote = result['indicators']['quote'][0]
        opens = quote.get('open', [])
        highs = quote.get('high', [])
        lows = quote.get('low', [])
        closes = quote.get('close', [])
        volumes = quote.get('volume', [])

        valid_days = []
        for i in range(len(timestamps)):
            if closes[i] is not None and not math.isnan(closes[i]):
                valid_days.append({
                    'timestamp': timestamps[i],
                    'date': datetime.fromtimestamp(timestamps[i]).strftime('%Y-%m-%d'),
                    'open': opens[i] if opens[i] is not None else closes[i],
                    'high': highs[i] if highs[i] is not None else closes[i],
                    'low': lows[i] if lows[i] is not None else closes[i],
                    'close': closes[i],
                    'volume': volumes[i] if volumes[i] is not None else 0
                })
        return valid_days
    except Exception as e:
        print(f"Error fetching data for {ticker}: {e}")
        return []

def calculate_point_in_time_indicators(history, t_idx):
    """
    Strictly compute indicators at index t_idx using ONLY data up to t_idx.
    Prevents any lookahead bias.
    """
    if t_idx < 20:
        return None

    current = history[t_idx]
    prev = history[t_idx - 1]
    
    # 1. 20-day Close Moving Average & Z-Score
    closes_20 = [history[i]['close'] for i in range(t_idx - 19, t_idx + 1)]
    mean_20 = sum(closes_20) / 20.0
    var_20 = sum((c - mean_20) ** 2 for c in closes_20) / 20.0
    std_20 = math.sqrt(var_20)
    z_score = (current['close'] - mean_20) / std_20 if std_20 > 0 else 0.0

    # 2. 5-day & 20-day Volume MAs
    vols_5 = [history[i]['volume'] for i in range(t_idx - 4, t_idx + 1)]
    vols_20 = [history[i]['volume'] for i in range(t_idx - 19, t_idx + 1)]
    vol_ma5 = sum(vols_5) / 5.0
    vol_ma20 = sum(vols_20) / 20.0
    vol_ratio5 = current['volume'] / vol_ma5 if vol_ma5 > 0 else 1.0

    # 3. 20-day Chaikin Money Flow (CMF)
    sum_mfv = 0.0
    sum_vol = 0.0
    for i in range(t_idx - 19, t_idx + 1):
        d = history[i]
        hl = d['high'] - d['low']
        mfm = (((d['close'] - d['low']) - (d['high'] - d['close'])) / hl) if hl > 0 else 0.0
        sum_mfv += mfm * d['volume']
        sum_vol += d['volume']
    cmf20 = sum_mfv / sum_vol if sum_vol > 0 else 0.0

    # 4. Volume-Price Pattern
    is_up = current['close'] >= prev['close']
    is_vol_up = current['volume'] >= prev['volume']

    if is_up and is_vol_up:
        vp_pattern = '價漲量增 (多方強攻)'
    elif is_up and not is_vol_up:
        vp_pattern = '價漲量縮 (追價謹慎/籌碼鎖定)'
    elif not is_up and is_vol_up:
        vp_pattern = '價跌量增 (賣壓湧現/調節出貨)'
    else:
        vp_pattern = '價跌量縮 (量縮整理/正常回檔)'

    if vol_ratio5 >= 2.0 and is_up:
        vp_pattern = '爆量長紅 (主力多頭突破)'
    elif vol_ratio5 >= 2.0 and not is_up:
        vp_pattern = '爆量長黑 (主力避險殺多/出貨)'
    elif vol_ratio5 <= 0.5:
        vp_pattern = '窒息量整理 (賣盤枯竭)'

    # 5. Smart Money / Whale Flow
    hl_curr = current['high'] - current['low']
    mfm_curr = (((current['close'] - current['low']) - (current['high'] - current['close'])) / hl_curr) if hl_curr > 0 else 0.0
    
    if mfm_curr >= 0.35 and vol_ratio5 >= 1.0:
        whale_flow = '大戶積極吃貨'
        retail_flow = '散戶惜售/換手'
    elif mfm_curr >= 0.1:
        whale_flow = '大戶小幅偏多'
        retail_flow = '散戶小量跟進'
    elif mfm_curr <= -0.35 and vol_ratio5 >= 1.0:
        whale_flow = '大戶調節出貨'
        retail_flow = '散戶套牢接刀'
    elif mfm_curr <= -0.1:
        whale_flow = '大戶減碼防守'
        retail_flow = '散戶逢低搶進'
    else:
        whale_flow = '大戶籌碼平衡'
        retail_flow = '散戶理性觀望'

    return {
        'date': current['date'],
        'close': current['close'],
        'open': current['open'],
        'high': current['high'],
        'low': current['low'],
        'volume': current['volume'],
        'z_score': z_score,
        'vol_ma5': vol_ma5,
        'vol_ma20': vol_ma20,
        'vol_ratio5': vol_ratio5,
        'cmf20': cmf20,
        'vp_pattern': vp_pattern,
        'whale_flow': whale_flow,
        'retail_flow': retail_flow
    }

def compute_quant_score(indicators, ticker, weights=(0.15, 0.27, 0.25, 0.33)):
    """
    Compute Quant Action Score (-2.00 to +2.00) based on weights.
    weights = (w_zscore, w_vp, w_inst, w_pcr)
    """
    if len(weights) == 4:
        w_z, w_vp, w_inst, w_pcr = weights
    else:
        w_z, w_vp, w_inst = weights[:3]
        w_pcr = 0.0

    z_score = indicators['z_score']
    vp_pattern = indicators['vp_pattern']
    whale_flow = indicators['whale_flow']
    cmf20 = indicators['cmf20']

    # 1. Z-Score Factor (Max 2.0 * w_z)
    z_max = 2.0 * w_z
    z_cont = -(z_score / 2.0) * z_max
    z_cont = max(-z_max, min(z_max, z_cont))

    # 2. Volume-Price Factor (Max 2.0 * w_vp)
    vp_max = 2.0 * w_vp
    if '價漲量增' in vp_pattern or '多頭突破' in vp_pattern:
        vp_cont = +1.0 * vp_max
    elif '價漲量縮' in vp_pattern:
        vp_cont = +0.22 * vp_max
    elif '窒息量' in vp_pattern or ('價跌量縮' in vp_pattern and z_score < 0):
        vp_cont = +0.75 * vp_max
    elif '價跌量縮' in vp_pattern and z_score >= 0:
        vp_cont = -0.22 * vp_max
    elif '價跌量增' in vp_pattern or '殺多' in vp_pattern or '出貨' in vp_pattern or '長黑' in vp_pattern:
        vp_cont = -1.0 * vp_max
    else:
        vp_cont = 0.0

    # 3. Smart Money / Institutional Factor (Max 2.0 * w_inst)
    inst_max = 2.0 * w_inst
    cmf_part = cmf20 * 1.0 * (inst_max * 0.6)
    cmf_part = max(-inst_max * 0.6, min(inst_max * 0.6, cmf_part))

    whale_part = 0.0
    if '吃貨' in whale_flow:
        whale_part = +0.40 * inst_max
    elif '偏多' in whale_flow:
        whale_part = +0.20 * inst_max
    elif '出貨' in whale_flow or '拋售' in whale_flow:
        whale_part = -0.40 * inst_max
    elif '減碼' in whale_flow:
        whale_part = -0.20 * inst_max
    
    inst_cont = max(-inst_max, min(inst_max, cmf_part + whale_part))

    # 4. Options PCR Factor (Max 2.0 * w_pcr)
    pcr_max = 2.0 * w_pcr
    sim_pcr = 0.85 - (z_score / 2.0) * 0.25
    if sim_pcr >= 1.25:
        pcr_cont = +1.0 * pcr_max
    elif sim_pcr >= 1.05:
        pcr_cont = +0.65 * pcr_max
    elif sim_pcr >= 0.75:
        pcr_cont = +0.35 * pcr_max
    elif sim_pcr >= 0.55:
        pcr_cont = -0.30 * pcr_max
    else:
        pcr_cont = -1.0 * pcr_max

    total_score = z_cont + vp_cont + inst_cont + pcr_cont

    # Leveraged ETF high deviation protection
    is_leveraged = ticker in ['SOXL', 'SOXS', 'TQQQ', 'SQQQ', 'NVDL', 'TSLL', 'FNGU']
    if is_leveraged and total_score > 0.6 and z_score > 1.2:
        total_score -= 0.30

    total_score = max(-2.0, min(2.0, total_score))

    return {
        'total_score': total_score,
        'z_cont': z_cont,
        'vp_cont': vp_cont,
        'inst_cont': inst_cont,
        'pcr_cont': pcr_cont
    }

def run_backtest_simulation(ticker, range_val="1y", weights=(0.15, 0.27, 0.25, 0.33)):
    """
    Run point-in-time walk-forward backtest across all trading days.
    Evaluates forward returns for Buy signals (+0.4 to +2.0) vs Sell signals (-2.0 to -0.4).
    """
    history = fetch_history(ticker, range_val)
    if len(history) < 25:
        print(f"Not enough historical data for {ticker}")
        return None

    trade_records = []
    
    for t in range(20, len(history)):
        ind = calculate_point_in_time_indicators(history, t)
        if not ind:
            continue
        
        score_res = compute_quant_score(ind, ticker, weights)
        score = score_res['total_score']
        current_close = ind['close']

        # Determine signal
        if score >= 1.0:
            signal = "STRONG_BUY"
        elif score >= 0.4:
            signal = "BUY"
        elif score <= -1.0:
            signal = "STRONG_SELL"
        elif score <= -0.4:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        # Calculate forward returns over 3d, 5d (1w), 10d (2w), 20d (1mo)
        fwd_returns = {}
        for fwd_days in [3, 5, 10, 20]:
            if t + fwd_days < len(history):
                fwd_close = history[t + fwd_days]['close']
                ret = ((fwd_close - current_close) / current_close) * 100.0
                fwd_returns[fwd_days] = ret
            else:
                fwd_returns[fwd_days] = None

        trade_records.append({
            'date': ind['date'],
            'index': t,
            'close': current_close,
            'z_score': ind['z_score'],
            'vp_pattern': ind['vp_pattern'],
            'whale_flow': ind['whale_flow'],
            'cmf20': ind['cmf20'],
            'score': score,
            'z_cont': score_res['z_cont'],
            'vp_cont': score_res['vp_cont'],
            'inst_cont': score_res['inst_cont'],
            'signal': signal,
            'fwd_returns': fwd_returns
        })

    return {
        'ticker': ticker,
        'history_len': len(history),
        'records': trade_records,
        'weights': weights
    }

def analyze_performance(backtest_res):
    """Compute win rate, average returns, Sharpe, and profitability metrics."""
    records = backtest_res['records']
    ticker = backtest_res['ticker']
    
    buy_signals = [r for r in records if r['signal'] in ['BUY', 'STRONG_BUY']]
    strong_buy_signals = [r for r in records if r['signal'] == 'STRONG_BUY']
    sell_signals = [r for r in records if r['signal'] in ['SELL', 'STRONG_SELL']]
    neutral_signals = [r for r in records if r['signal'] == 'NEUTRAL']

    stats = {}
    for fwd_days in [3, 5, 10, 20]:
        # Buy signals forward returns
        buy_rets = [r['fwd_returns'][fwd_days] for r in buy_signals if r['fwd_returns'][fwd_days] is not None]
        strong_buy_rets = [r['fwd_returns'][fwd_days] for r in strong_buy_signals if r['fwd_returns'][fwd_days] is not None]
        sell_rets = [r['fwd_returns'][fwd_days] for r in sell_signals if r['fwd_returns'][fwd_days] is not None]
        all_rets = [r['fwd_returns'][fwd_days] for r in records if r['fwd_returns'][fwd_days] is not None]

        buy_win = (len([r for r in buy_rets if r > 0]) / len(buy_rets) * 100.0) if buy_rets else 0.0
        strong_buy_win = (len([r for r in strong_buy_rets if r > 0]) / len(strong_buy_rets) * 100.0) if strong_buy_rets else 0.0
        avg_buy_ret = (sum(buy_rets) / len(buy_rets)) if buy_rets else 0.0
        avg_strong_buy_ret = (sum(strong_buy_rets) / len(strong_buy_rets)) if strong_buy_rets else 0.0
        avg_sell_ret = (sum(sell_rets) / len(sell_rets)) if sell_rets else 0.0
        avg_benchmark_ret = (sum(all_rets) / len(all_rets)) if all_rets else 0.0

        stats[fwd_days] = {
            'buy_count': len(buy_rets),
            'buy_win_rate': buy_win,
            'buy_avg_return': avg_buy_ret,
            'strong_buy_count': len(strong_buy_rets),
            'strong_buy_win_rate': strong_buy_win,
            'strong_buy_avg_return': avg_strong_buy_ret,
            'sell_count': len(sell_rets),
            'sell_avg_return': avg_sell_ret,
            'benchmark_avg_return': avg_benchmark_ret,
            'alpha_over_benchmark': avg_buy_ret - avg_benchmark_ret
        }

    return stats

def simulate_random_rollback(backtest_res, sample_count=5):
    """
    Rollback to random past dates and show exact gauge reading and forward outcome.
    """
    records = backtest_res['records']
    ticker = backtest_res['ticker']
    
    # Filter records with available 10d future data
    valid_candidates = [r for r in records if r['fwd_returns'][5] is not None and r['fwd_returns'][10] is not None]
    if not valid_candidates:
        return []

    sampled = random.sample(valid_candidates, min(sample_count, len(valid_candidates)))
    results = []

    for r in sampled:
        score = r['score']
        signal = r['signal']
        date_str = r['date']
        close = r['close']
        ret_3d = r['fwd_returns'][3]
        ret_5d = r['fwd_returns'][5]
        ret_10d = r['fwd_returns'][10]
        ret_20d = r['fwd_returns'].get(20)

        # Evaluate if gauge action was profitable
        if signal in ['BUY', 'STRONG_BUY']:
            profitable_1w = (ret_5d > 0)
            profitable_2w = (ret_10d > 0) if ret_10d is not None else None
            action_desc = f"【買進建議】Score: {score:+.2f} ({signal})"
        elif signal in ['SELL', 'STRONG_SELL']:
            # Selling is beneficial if price drops or underperforms
            profitable_1w = (ret_5d <= 0)
            profitable_2w = (ret_10d <= 0) if ret_10d is not None else None
            action_desc = f"【賣出/避險】Score: {score:+.2f} ({signal})"
        else:
            profitable_1w = None
            profitable_2w = None
            action_desc = f"【觀望持平】Score: {score:+.2f} (NEUTRAL)"

        results.append({
            'date': date_str,
            'ticker': ticker,
            'close_on_date': close,
            'score': score,
            'z_score': r['z_score'],
            'vp_pattern': r['vp_pattern'],
            'whale_flow': r['whale_flow'],
            'signal': signal,
            'action_desc': action_desc,
            'ret_3d': ret_3d,
            'ret_5d_1w': ret_5d,
            'ret_10d_2w': ret_10d,
            'ret_20d_1mo': ret_20d,
            'profitable_1w': profitable_1w,
            'profitable_2w': profitable_2w
        })

    return results

def run_weight_sensitivity_analysis(ticker, range_val="1y"):
    """
    Compare performance of different weight combinations:
    A: 100% Z-Score (Single Factor)
    B: 50% Volume-Price + 50% Smart Money (No Z-Score)
    C: Current Model (35% Z-Score + 32.5% Volume-Price + 32.5% Smart Money)
    D: Equal Weight (34% Z-Score + 33% Volume-Price + 33% Smart Money)
    E: High Z-Score (70% Z-Score + 15% Volume-Price + 15% Smart Money)
    """
    weight_sets = {
        "A. 純 100% Z-Score 均線乖離": (1.00, 0.00, 0.00),
        "B. 純 50%量價 + 50%大戶籌碼 (無Z-Score)": (0.00, 0.50, 0.50),
        "C. 現行模型 (35% Z-Score + 32.5% 量價 + 32.5% 大戶)": (0.35, 0.325, 0.325),
        "D. 平均權重 (34% Z-Score + 33% 量價 + 33% 大戶)": (0.34, 0.33, 0.33),
        "E. 高乖離權重 (70% Z-Score + 15% 量價 + 15% 大戶)": (0.70, 0.15, 0.15)
    }

    comparison = {}
    for name, w in weight_sets.items():
        bt = run_backtest_simulation(ticker, range_val=range_val, weights=w)
        if bt:
            stats = analyze_performance(bt)
            comparison[name] = {
                'weights': w,
                'stats': stats
            }

    return comparison

def main():
    tickers = ['SOXL', 'TSM', 'MU', 'NVDA']
    if len(sys.argv) > 1:
        tickers = [sys.argv[1].upper()]

    print("=" * 80)
    print(" 🚀 Quant Action Gauge 量化買賣模型回測與權重驗證系統")
    print("=" * 80)

    for ticker in tickers:
        print(f"\n▶ 正在測試標的：{ticker} (近 1 年歷史數據逐日點對點回測)")
        print("-" * 80)

        # 1. 執行現行模型回測
        bt = run_backtest_simulation(ticker, range_val="1y", weights=(0.35, 0.325, 0.325))
        if not bt:
            continue

        stats = analyze_performance(bt)

        print(f"【現行權重模型表現 (Z-Score 35% + 量價 32.5% + 機構 32.5%)】")
        print(f"{'週期':<10} | {'買進次數':<8} | {'買進勝率':<10} | {'平均報酬率':<12} | {'大盤基準報酬':<12} | {'超額Alpha':<10}")
        print("-" * 75)
        for days in [3, 5, 10, 20]:
            s = stats[days]
            period_label = f"後續 {days} 天" + (" (1週)" if days == 5 else (" (2週)" if days == 10 else (" (1月)" if days == 20 else "")))
            print(f"{period_label:<10} | {s['buy_count']:<8} | {s['buy_win_rate']:>6.1f}%   | {s['buy_avg_return']:>+8.2f}%   | {s['benchmark_avg_return']:>+8.2f}%   | {s['alpha_over_benchmark']:>+8.2f}%")

        # 2. 隨機回溯抽樣模擬展示
        print(f"\n▶ 隨機歷史日期回溯模擬 (Rollback Simulation)：")
        samples = simulate_random_rollback(bt, sample_count=4)
        for idx, sp in enumerate(samples, 1):
            profit_icon = "🟢 獲利" if sp['ret_5d_1w'] > 0 else "🔴 虧損"
            print(f"  [{idx}] 歷史日期: {sp['date']} (收盤價: ${sp['close_on_date']:.2f})")
            print(f"      當日儀表評分: {sp['score']:+.2f} ({sp['signal']}) | Z-Score: {sp['z_score']:.2f} | 量價: {sp['vp_pattern']}")
            print(f"      1週後 (+5天) 漲跌: {sp['ret_5d_1w']:+.2f}% ({profit_icon}) | 2週後 (+10天): {sp['ret_10d_2w']:+.2f}% | 1月後 (+20天): {sp['ret_20d_1mo'] if sp['ret_20d_1mo'] is not None else 0:+.2f}%")

        # 3. 權重敏感度分析比較
        print(f"\n▶ 權重合理性與敏感度對比分析 (Weight Sensitivity Comparison - 後續 1 週報酬)：")
        sens = run_weight_sensitivity_analysis(ticker, range_val="1y")
        print(f"{'模型權重組合':<38} | {'1週勝率':<10} | {'1週平均報酬':<12} | {'超額Alpha':<10}")
        print("-" * 75)
        for name, data in sens.items():
            s5 = data['stats'][5]
            print(f"{name:<38} | {s5['buy_win_rate']:>6.1f}%   | {s5['buy_avg_return']:>+8.2f}%   | {s5['alpha_over_benchmark']:>+8.2f}%")

    print("\n" + "=" * 80)
    print(" ✅ 回測與驗證完成！")
    print("=" * 80)

if __name__ == '__main__':
    main()
