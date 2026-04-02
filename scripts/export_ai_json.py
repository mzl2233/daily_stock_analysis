#!/usr/bin/env python3
"""Export analysis results as JSON for dashboard consumption."""
import json
import re
import os
from datetime import datetime, timezone, timedelta

def parse_report(report_path):
    with open(report_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    stocks = []
    # Parse each stock section
    sections = re.split(r'^## [🟡🔴🟢]', content, flags=re.MULTILINE)
    
    for section in sections[1:]:  # Skip the header
        name_match = re.search(r'^\s*(.+?)\s*\((\d{6})\)', section, re.MULTILINE)
        if not name_match:
            continue
        
        name = name_match.group(1).strip()
        code = name_match.group(2)
        
        # Signal
        signal = "持有"
        signal_type = "hold"
        if "买入" in section[:200] or "🟢 买入" in section[:200]:
            signal = "买入"
            signal_type = "buy"
        elif "卖出" in section[:200] or "🔴 卖出" in section[:200]:
            signal = "卖出"
            signal_type = "sell"
        
        # Score
        score_match = re.search(r'评分\s*(\d+)', section)
        score = int(score_match.group(1)) if score_match else 50
        
        # Trend
        trend_match = re.search(r'\*\*\w+\*\*\s*\|\s*(\w+)', section)
        trend = trend_match.group(1) if trend_match else "震荡"
        
        # Prices from table
        price = support = resistance = ma5 = ma10 = ma20 = bias = None
        price_match = re.search(r'当前价\s*\|\s*([\d.]+)', section)
        if price_match:
            price = float(price_match.group(1))
        
        ma5_match = re.search(r'MA5\s*\|\s*([\d.]+)', section)
        if ma5_match:
            ma5 = float(ma5_match.group(1))
        
        ma10_match = re.search(r'MA10\s*\|\s*([\d.]+)', section)
        if ma10_match:
            ma10 = float(ma10_match.group(1))
        
        ma20_match = re.search(r'MA20\s*\|\s*([\d.]+)', section)
        if ma20_match:
            ma20 = float(ma20_match.group(1))
        
        bias_match = re.search(r'乖离率.*?([\d.-]+)%', section)
        if bias_match:
            bias = float(bias_match.group(1))
        
        support_match = re.search(r'支撑位\s*\|\s*([\d.]+|N/A)', section)
        if support_match and support_match.group(1) != 'N/A':
            support = float(support_match.group(1))
        
        resistance_match = re.search(r'压力位\s*\|\s*([\d.]+|N/A)', section)
        if resistance_match and resistance_match.group(1) != 'N/A':
            resistance = float(resistance_match.group(1))
        
        # Conclusion
        conclusion = ""
        conc_match = re.search(r'一句话决策\*\*:\s*(.+)', section)
        if conc_match:
            conclusion = conc_match.group(1).strip()
            if "分析过程出错" in conclusion:
                conclusion = f"{trend}，等待下次分析"
        
        stocks.append({
            "code": code,
            "name": name,
            "signal": signal,
            "signal_type": signal_type,
            "score": score,
            "trend": trend,
            "price": price,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "bias": bias,
            "support": support,
            "resistance": resistance,
            "conclusion": conclusion or f"{trend}，观望为主"
        })
    
    return stocks

def parse_market_review(review_path):
    if not os.path.exists(review_path):
        return None
    with open(review_path, 'r', encoding='utf-8') as f:
        content = f.read()
    # Extract first meaningful line as summary
    lines = content.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line and not line.startswith('#') and not line.startswith('>'):
            return line[:100]
    return None

def main():
    report_dir = os.environ.get('REPORT_DIR', 'reports')
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    
    report_path = os.path.join(report_dir, f'report_{today.replace("-","")}.md')
    review_path = os.path.join(report_dir, f'market_review_{today.replace("-","")}.md')
    
    if not os.path.exists(report_path):
        print(f"Report not found: {report_path}")
        return
    
    stocks = parse_report(report_path)
    market_review = parse_market_review(review_path)
    
    buy = sum(1 for s in stocks if s['signal_type'] == 'buy')
    hold = sum(1 for s in stocks if s['signal_type'] == 'hold')
    sell = sum(1 for s in stocks if s['signal_type'] == 'sell')
    
    tz = timezone(timedelta(hours=8))
    result = {
        "date": today,
        "generated_at": datetime.now(tz).isoformat(),
        "summary": {
            "total": len(stocks),
            "buy": buy,
            "hold": hold,
            "sell": sell,
            "market_review": market_review or "暂无大盘复盘"
        },
        "stocks": stocks
    }
    
    output_path = 'reports/latest.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Exported {len(stocks)} stocks to {output_path}")

if __name__ == '__main__':
    main()
