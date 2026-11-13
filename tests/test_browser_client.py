import shutil
import subprocess
import unittest
from pathlib import Path


class BrowserClientTests(unittest.TestCase):
    def test_home_ranking_uses_period_points(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for JS runtime regression')
        source = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text(
            encoding='utf-8'
        )
        body = source.split("      function update(data,period='day') {", 1)[1].split(
            '      function task(', 1
        )[0]
        script = (
            "const assert=require('node:assert/strict');let live;const render=()=>{};function update(data,period='day'){"
            + body
            + """
const data={loaded:true,schools:[],classes:[],users:[
 {name:'Older',points:100,day_points:0,week_points:100},
 {name:'Today',points:5,day_points:5,week_points:5}]};
update(data,'day');assert.deepEqual(live.users[0],['Today',5]);
update(data,'week');assert.deepEqual(live.users[0],['Older',100]);
"""
        )
        result = subprocess.run([node, '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_factory_reuses_canonical_url_and_replaces_changed_key(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node is needed for JS runtime regression')
        source = (Path(__file__).resolve().parents[1] / 'web/index.html').read_text(
            encoding='utf-8'
        )
        function = source.split('    function ensureClient() {', 1)[1].split(
            '    async function rpc', 1
        )[0]
        script = (
            """
const assert=require('node:assert/strict');
let client=null,clientConfig=null,task=null,calls=[],stops=0;
const state={url:'http://localhost:54321/',key:'first'};
const window={supabase:{createClient:(url,key)=>{calls.push([url,key]);return {auth:{stopAutoRefresh:()=>stops++}}}}};
const drawProfile=()=>{},show=()=>{};
function ensureClient() {
"""
            + function
            + """
ensureClient();ensureClient();assert.equal(calls.length,1);
state.url='http://localhost:54321';ensureClient();assert.equal(calls.length,1);
state.key='second';ensureClient();assert.equal(calls.length,2);
state.url='http://127.0.0.1:54321';ensureClient();assert.equal(calls.length,3);
assert.equal(stops,2);assert.deepEqual(calls[1],['http://localhost:54321','second']);
"""
        )
        result = subprocess.run([node, '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
