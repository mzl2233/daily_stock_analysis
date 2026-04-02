#!/usr/bin/env python3
"""Push analysis results to Feishu bitable and send webhook notification."""
import json
import os
import re
import requests
from datetime import datetime, timezone, timedelta

# Config from env
FEISHU_WEBHOOK = os.environ.get('FEISHU_WEBHOOK_URL', '')
FEISHU_APP_ID = os.environ.get('FEISHU_APP_ID', '')
FEISHU_APP_SECRET = os.environ.get('FEISHU_APP_SECRET', '')
BITABLE_APP_TOKEN = 'DMnWbzroQa63dtsaJ2ic5p8Mn9d'
BITABLE_TABLE_ID = 'tbl1usYgZBZcxTAO'

def get_tenant_token():
    """Get Feishu tenant access token."""
    resp = requests.post(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json={'app_id': FEISHU_APP_ID, 'app_secret': FEISHU_APP_SECRET}
    )
    return resp.json().get('tenant_access_token', '')

def push_to_bitable(token, data):
    """Write analysis records to Feishu bitable."""
    if not token:
        print("⚠️ No Feishu token, skipping bitable write")
        return
    
    tz = timezone(timedelta(hours=8))
    today_str = datetime.now(tz).strftime('%Y-%m-%d')
    # Convert to timestamp in ms for Feishu date field
    today_ts = int(datetime.now(tz).replace(hour=0, minute=0, second=0).timestamp() * 1000)
    
    market_review = data.get('summary', {}).get('market_review', '')
    
    records = []
    for st in data.get('stocks', []):
        signal_map = {'buy': '买入', 'hold': '持有', 'sell': '卖出'}
        records.append({
            'fields': {
                '日期': today_ts,
                '股票名称': st.get('name', ''),
                '股票代码': st.get('code', ''),
                '信号': signal_map.get(st.get('signal_type', 'hold'), '持有'),
                '评分': st.get('score', 50),
                '趋势': st.get('trend', ''),
                '现价': st.get('price'),
                '支撑位': st.get('support'),
                '压力位': st.get('resistance'),
                'MA5': st.get('ma5'),
                '乖离率': st.get('bias'),
                '结论': st.get('conclusion', ''),
                '大盘观点': market_review
            }
        })
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # Batch create records
    resp = requests.post(
        f'https://open.feishu.cn/open-apis/bitable/v1/apps/{BITABLE_APP_TOKEN}/tables/{BITABLE_TABLE_ID}/records/batch_create',
        headers=headers,
        json={'records': records}
    )
    
    result = resp.json()
    if result.get('code') == 0:
        print(f"✅ 已写入 {len(records)} 条记录到飞书多维表格")
    else:
        print(f"❌ 飞书表格写入失败: {result.get('msg', 'unknown error')}")

def send_webhook(data):
    """Send formatted report to Feishu group via webhook."""
    if not FEISHU_WEBHOOK:
        print("⚠️ No webhook URL, skipping notification")
        return
    
    s = data.get('summary', {})
    stocks = data.get('stocks', [])
    date = data.get('date', '--')
    
    # Build message lines
    lines = [f"📊 智投看板 · {date}", ""]
    lines.append(f"🟢 买入: {s.get('buy', 0)}  🟡 观望: {s.get('hold', 0)}  🔴 卖出: {s.get('sell', 0)}")
    lines.append("")
    
    if s.get('market_review'):
        lines.append(f"📈 大盘观点: {s['market_review']}")
        lines.append("")
    
    for st in stocks:
        emoji = {'buy': '🟢', 'sell': '🔴', 'hold': '🟡'}.get(st.get('signal_type'), '🟡')
        price = st.get('price', '--')
        signal = st.get('signal', '持有')
        score = st.get('score', '--')
        conclusion = st.get('conclusion', '--')
        
        lines.append(f"{emoji} {st.get('name', '')} ({st.get('code', '')})  现价 {price}")
        lines.append(f"   {signal} | 评分 {score} | {conclusion}")
    
    lines.append("")
    lines.append("📋 完整数据: https://my.feishu.cn/base/DMnWbzroQa63dtsaJ2ic5p8Mn9d")
    
    text = '\n'.join(lines)
    
    resp = requests.post(FEISHU_WEBHOOK, json={
        'msg_type': 'text',
        'content': {'text': text}
    })
    
    if resp.status_code == 200:
        result = resp.json()
        if result.get('code') == 0 or result.get('StatusCode') == 0:
            print("✅ 飞书群通知已发送")
        else:
            print(f"❌ 飞书通知失败: {result}")
    else:
        print(f"❌ 飞书通知 HTTP 错误: {resp.status_code}")

def main():
    report_dir = os.environ.get('REPORT_DIR', 'reports')
    today = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')
    
    report_path = os.path.join(report_dir, f'report_{today}.md')
    json_path = 'reports/latest.json'
    
    # Load JSON data
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    elif os.path.exists(report_path):
        print("⚠️ latest.json not found, skipping")
        return
    else:
        print("⚠️ No report found")
        return
    
    # Get Feishu token
    token = get_tenant_token() if FEISHU_APP_ID and FEISHU_APP_SECRET else ''
    
    # Push to bitable
    push_to_bitable(token, data)
    
    # Send webhook
    send_webhook(data)

if __name__ == '__main__':
    main()
