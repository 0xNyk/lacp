#!/usr/bin/env zsh
# Fetches X bookmarks via SSH to jarv using X API v2 OAuth.
# Outputs JSON to stdout, errors to stderr.
# Uses the existing OAuth tokens on jarv (xint skill).
#
# Usage: ./fetch_x_bookmarks.sh [--limit N]
#
set -euo pipefail

LIMIT="${1:-50}"
if [[ "$LIMIT" == "--limit" ]]; then
  LIMIT="${2:-50}"
fi

ssh jarv "python3 -c \"
import json, os, urllib.request, urllib.parse, sys

TOKEN_PATHS=[
    '/home/openclaw/.openclaw/workspace-jarv/skills/xint/data/oauth-tokens.json',
    '/home/openclaw/.openclaw/skills/xint/data/oauth-tokens.json',
]

token = None
for p in TOKEN_PATHS:
    if os.path.exists(p):
        with open(p) as f:
            t = json.load(f)
        token = t.get('access_token') or t.get('accessToken')
        if token:
            break

if not token:
    print(json.dumps({'error': 'no_oauth_token'}))
    sys.exit(1)

headers = {'Authorization': f'Bearer {token}'}

# Get user ID
req = urllib.request.Request('https://api.x.com/2/users/me?user.fields=username', headers=headers)
me = json.loads(urllib.request.urlopen(req, timeout=15).read())
uid = me['data']['id']

# Fetch bookmarks with pagination up to limit
all_tweets = []
all_users = {}
next_token = None
remaining = ${LIMIT}

while remaining > 0:
    batch = min(remaining, 100)
    params = {
        'max_results': str(batch),
        'expansions': 'author_id',
        'tweet.fields': 'created_at,public_metrics,entities',
        'user.fields': 'username,name'
    }
    if next_token:
        params['pagination_token'] = next_token

    url = 'https://api.x.com/2/users/' + uid + '/bookmarks?' + urllib.parse.urlencode(params)
    req2 = urllib.request.Request(url, headers=headers)
    data = json.loads(urllib.request.urlopen(req2, timeout=30).read())

    tweets = data.get('data', []) or []
    users = {u['id']: u for u in data.get('includes', {}).get('users', []) if 'id' in u}
    all_tweets.extend(tweets)
    all_users.update(users)
    remaining -= len(tweets)

    next_token = data.get('meta', {}).get('next_token')
    if not next_token or not tweets:
        break

print(json.dumps({'data': all_tweets, 'includes': {'users': list(all_users.values())}}, ensure_ascii=False))
\"" 2>/dev/null
