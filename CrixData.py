import json
import urllib.request
from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def home():
    matches = {'live': [], 'upcoming': [], 'finished': []}
    
    try:
        url = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/scoreboard"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            for evt in data.get('events', []):
                comp = evt.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                
                t1 = competitors[0].get('team', {}).get('displayName', 'TBD') if len(competitors) > 0 else 'TBD'
                t1_score = competitors[0].get('score', 'Yet to Bat') if len(competitors) > 0 else 'Yet to Bat'
                
                t2 = competitors[1].get('team', {}).get('displayName', 'TBD') if len(competitors) > 1 else 'TBD'
                t2_score = competitors[1].get('score', 'Yet to Bat') if len(competitors) > 1 else 'Yet to Bat'
                
                status_type = comp.get('status', {}).get('type', {})
                state = status_type.get('state', 'pre')
                status_desc = status_type.get('detail', status_type.get('shortDetail', 'Scheduled'))
                
                venue = comp.get('venue', {}).get('fullName', 'Stadium N/A')
                name_str = (evt.get('name', '') + ' ' + comp.get('type', {}).get('text', '')).lower()
                
                if 'test' in name_str:
                    fmt = 'TEST'
                elif 'odi' in name_str or 'one day' in name_str:
                    fmt = 'ODI'
                else:
                    fmt = 'T20'
                
                match_data = {
                    'title': evt.get('name', f"{t1} vs {t2}"),
                    't1': t1, 't1_score': t1_score,
                    't2': t2, 't2_score': t2_score,
                    'status': status_desc,
                    'venue': venue,
                    'format': fmt,
                    'date': evt.get('date', '')[:10]
                }
                
                if state == 'in':
                    matches['live'].append(match_data)
                elif state == 'post':
                    matches['finished'].append(match_data)
                else:
                    matches['upcoming'].append(match_data)
                    
    except Exception as e:
        print("Backend Fetch Error:", e)

    return render_template('index.html', matches=matches)

if __name__ == '__main__':
    app.run(debug=True)