"""Visual browser inspection with API-contract fixture playback.

In some automated environments Chromium cannot navigate to 127.0.0.1.
For visual verification only, this embeds the real web assets and supplies API
responses generated from the real Python engine. Runtime API integration is
separately tested in test_engine.py and via curl.
"""
import json
import re
import sys
import tempfile
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine import connect,init,overview,issues,issue_detail,issue_similarity,recent_runs,run_detail,release_report,generate_run
from main import route_api

with connect(ROOT/'data'/'matchpulse.db') as db:
    config=route_api(db,'GET','/api/config')[1]
    snapshots={f'{days}/{plat}':overview(db,days,plat) for days in [7,14,30] for plat in ['All','PC','PlayStation','Xbox']}
    items=issues(db,limit=150)
    details={str(x['id']):{**issue_detail(db,x['id']),'similar':issue_similarity(db,x['id'])} for x in items}
    runs=recent_runs(db)
    report={f'{days}/{plat}':release_report(db,days,plat) for days in [7,14,30] for plat in ['All','PC','PlayStation','Xbox']}
    with tempfile.TemporaryDirectory() as temp:
        with connect(Path(temp)/'visual.db') as visual_db:
            init(visual_db)
            run=run_detail(visual_db,generate_run(visual_db,'Gameplay Smoke','PC',777))
    run_list=recent_runs(db)
    values={'config':config,'snapshots':snapshots,'issues':items,'details':details,'runs':run_list,'run':run,'reports':report}

mock_js='''(() => {
const data = __FIXTURES__;
const respond=(body,status=200,type='application/json')=>Promise.resolve(new Response(type==='application/json'?JSON.stringify(body):body,{status,headers:{'content-type':type}}));
window.fetch=async(url,opts={})=>{
 const u=new URL(url,'http://matchpulse.example');
 const p=u.pathname;
 if(p==='/api/config')return respond(data.config);
 if(p==='/api/overview')return respond(data.snapshots[(u.searchParams.get('days')||'14')+'/'+(u.searchParams.get('platform')||'All')]);
 if(p==='/api/issues'){
   const q=(u.searchParams.get('search')||'').toLowerCase();
   const arr=data.issues.filter(i=>(!q||i.title.toLowerCase().includes(q)||i.description.toLowerCase().includes(q)||String(i.id).includes(q))&&
     ['severity','status','feature','platform'].every(k=>(u.searchParams.get(k)||'All')==='All'||i[k]===(u.searchParams.get(k))));
   return respond({issues:arr});
 }
 if(p.match(/^\\/api\\/issues\\/\\d+$/)){
    const id=p.split('/').pop();
    if(opts.method==='PATCH'){
       const update=JSON.parse(opts.body);data.details[id][update.field]=update.value;const row=data.issues.find(x=>String(x.id)===id);row[update.field]=update.value;return respond(data.details[id]);
    }
    return respond(data.details[id]||{error:'Not found'}, data.details[id]?200:404);
 }
 if(p==='/api/runs')return opts.method==='POST'?respond(data.run,201):respond({runs:data.runs});
 if(p==='/api/report.md')return respond(data.reports[(u.searchParams.get('days')||'14')+'/'+(u.searchParams.get('platform')||'All')],200,'text/markdown');
 if(p==='/api/issues.csv')return respond('id,title\\n1,Sample',200,'text/csv');
 return respond({error:'No mock route: '+p},404);
};
})();'''.replace('__FIXTURES__',json.dumps(values,ensure_ascii=False))

html=(ROOT/'web'/'index.html').read_text()
html=re.sub(r'<link rel="stylesheet"[^>]+>','',html)
html=re.sub(r'<link rel="icon"[^>]+>','',html)
html=re.sub(r'<script src="/app.js" defer></script>','',html)

with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=b.new_page(viewport={'width':1512,'height':1024},device_scale_factor=1)
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    css=(ROOT/'web'/'style.css').read_text().split('\n',1)[1]
    app=(ROOT/'web'/'app.js').read_text()
    html=html.replace('</head>', '<style>'+css+'</style></head>')
    html=html.replace('</body>', '<script>'+mock_js+'</script><script>'+app+'</script></body>')
    page.set_content(html,wait_until='domcontentloaded')
    page.wait_for_selector('.hero')
    page.wait_for_timeout(380)
    page.screenshot(path=str(ROOT/'docs'/'dashboard.png'),full_page=True)
    page.screenshot(path=str(ROOT/'docs'/'overview-viewport.png'),full_page=False)
    print('Dashboard title:',page.locator('.page-title').first.inner_text())
    print('Statistics cards:',page.locator('.stat-card').count())
    page.locator('[data-page="defects"]').click()
    page.wait_for_selector('#issue-search')
    print('Defect rows:',page.locator('#page-defects table tbody tr').count())
    page.locator('#page-defects table tbody tr').first.click()
    page.wait_for_selector('#drawer-status')
    print('Duplicate suggestions:',page.locator('.candidate').count())
    page.wait_for_timeout(380)
    page.screenshot(path=str(ROOT/'docs'/'defect-triage.png'),full_page=False)
    page.locator('#drawer-close').click()
    page.locator('[data-page="lab"]').click()
    page.wait_for_selector('#run-suite')
    page.locator('#lab-suite').select_option('Gameplay Smoke')
    page.locator('#lab-seed').fill('777')
    page.locator('#run-suite').click()
    page.wait_for_function('() => document.querySelectorAll("#page-lab .test-case").length === 10',timeout=10000)
    print('Lab result cases:',page.locator('#page-lab .test-case').count())
    page.wait_for_timeout(380)
    page.screenshot(path=str(ROOT/'docs'/'scenario-lab.png'),full_page=True)
    page.screenshot(path=str(ROOT/'docs'/'lab-viewport.png'),full_page=False)
    page.locator('[data-page="analytics"]').click()
    page.wait_for_selector('#page-analytics .line-chart')
    print('Analytics charts:',page.locator('#page-analytics .line-chart').count())
    page.wait_for_timeout(380)
    page.screenshot(path=str(ROOT/'docs'/'analytics-viewport.png'),full_page=False)
    page.locator('[data-page="report"]').click()
    page.wait_for_selector('#page-report .report-preview')
    page.wait_for_function('() => document.querySelector("#report-preview")?.innerText.includes("QUALITY RELEASE BRIEF")')
    print('Report generated:',page.locator('#report-preview').inner_text()[:36])
    page.wait_for_timeout(380)
    page.screenshot(path=str(ROOT/'docs'/'release-brief.png'),full_page=True)
    page.screenshot(path=str(ROOT/'docs'/'report-viewport.png'),full_page=False)
    print('JavaScript errors:',errors)
    assert not errors
    b.close()
