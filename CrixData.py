import json
import urllib.request
from flask import Flask, render_template

app = Flask(__name__)

def fetch_data(url):
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except Exception as e:
        print(f"Fetch Error for {url}: {e}")
        return None

@app.route('/')
def home():
    matches = {'live': [], 'upcoming': [], 'finished': []}
    
    # Primary & Secondary APIs to avoid 404
    urls = [
        "https://site.api.espn.com/apis/site/v2/sports/cricket/13840/scoreboard", # International Cricket
        "https://site.web.api.espn.com/apis/site/v2/sports/cricket/scoreboard"
    ]
    
    data = None
    for url in urls:
        res = fetch_data(url)
        if res and 'events' in res:
            data = res
            break
            
    if data:
        for evt in data.get('events', []):
            comp = evt.get('competitions', [{}])[0]
            competitors = comp.get('competitors', [])
            
            t1_name = competitors[0].get('team', {}).get('shortDisplayName', competitors[0].get('team', {}).get('displayName', 'TBD')) if len(competitors) > 0 else 'TBD'
            t1_score = competitors[0].get('score', '') if len(competitors) > 0 else ''
            
            t2_name = competitors[1].get('team', {}).get('shortDisplayName', competitors[1].get('team', {}).get('displayName', 'TBD')) if len(competitors) > 1 else 'TBD'
            t2_score = competitors[1].get('score', '') if len(competitors) > 1 else ''
            
            status_type = comp.get('status', {}).get('type', {})
            state = status_type.get('state', 'pre')
            status_desc = status_type.get('detail', status_type.get('shortDetail', 'Scheduled'))
            
            venue = comp.get('venue', {}).get('fullName', 'Stadium N/A')
            
            match_data = {
                'title': evt.get('name', f"{t1_name} vs {t2_name}"),
                't1': t1_name, 't1_score': t1_score if t1_score else 'Yet to bat',
                't2': t2_name, 't2_score': t2_score if t2_score else 'Yet to bat',
                'status': status_desc,
                'venue': venue,
                'date': evt.get('date', '')[:10]
            }
            
            if state == 'in':
                matches['live'].append(match_data)
            elif state == 'post':
                matches['finished'].append(match_data)
            else:
                matches['upcoming'].append(match_data)

    return render_template('index.html', matches=matches)

if __name__ == '__main__':
    app.run(debug=True)
