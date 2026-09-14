import json
import urllib.request
from datetime import datetime
import pytz
from flask import Flask, render_template

app = Flask(__name__)

def fetch_global_cricket():
    # ESPN Global Scoreboard (Covers IPL, CPL, BBL, Test, ODI, T20, Men, Women, U19)
    url = "https://site.web.api.espn.com/apis/site/v2/sports/cricket/13840/scoreboard"
    matches = {'live': [], 'upcoming': [], 'finished': []}
    
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            for evt in data.get('events', []):
                comp = evt.get('competitions', [{}])[0]
                competitors = comp.get('competitors', [])
                
                # Team details
                t1 = competitors[0].get('team', {}).get('displayName', 'Team A') if len(competitors) > 0 else 'Team A'
                t1_score = competitors[0].get('score', '') if len(competitors) > 0 else ''
                
                t2 = competitors[1].get('team', {}).get('displayName', 'Team B') if len(competitors) > 1 else 'Team B'
                t2_score = competitors[1].get('score', '') if len(competitors) > 1 else ''
                
                # Match status & state
                status_obj = comp.get('status', {})
                state = status_obj.get('type', {}).get('state', 'pre')  # 'in', 'pre', 'post'
                status_detail = status_obj.get('type', {}).get('detail', '')
                
                # Venue & Date Formatting
                venue = comp.get('venue', {}).get('fullName', 'Venue TBD')
                raw_date = evt.get('date', '')
                
                # Time conversion to IST and Local
                ist_time = "TBD"
                match_day = ""
                if raw_date:
                    try:
                        utc_dt = datetime.strptime(raw_date, "%Y-%m-%dT%H:%MZ").replace(tzinfo=pytz.utc)
                        ist_dt = utc_dt.astimezone(pytz.timezone('Asia/Kolkata'))
                        ist_time = ist_dt.strftime("%I:%M %p IST")
                        match_day = ist_dt.strftime("%A, %b %d, %Y")
                    except:
                        match_day = raw_date[:10]

                series_name = evt.get('season', {}).get('slug', 'Cricket Series').upper().replace('-', ' ')
                
                match_info = {
                    'title': evt.get('name', f"{t1} vs {t2}"),
                    'series': series_name,
                    't1': t1,
                    't1_score': t1_score if t1_score else 'Yet to bat',
                    't2': t2,
                    't2_score': t2_score if t2_score else 'Yet to bat',
                    'status': status_detail,
                    'venue': venue,
                    'day': match_day,
                    'ist_time': ist_time
                }
                
                # Strict Section Categorization
                if state == 'in':
                    matches['live'].append(match_info)
                elif state == 'post':
                    matches['finished'].append(match_info)
                else:
                    matches['upcoming'].append(match_info)
                    
    except Exception as e:
        print(f"Error fetching matches: {e}")
        
    return matches

@app.route('/')
def home():
    matches = fetch_global_cricket()
    return render_template('index.html', matches=matches)

if __name__ == '__main__':
    app.run(debug=True)
