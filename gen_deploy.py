"""Generate deploy_cloud.py with embedded base64 frontend files."""
import base64, pathlib

ROOT = pathlib.Path("D:/MyAgent-main")

files = {
    'frontend/src/views/ChatView.vue': ROOT / 'frontend/src/views/ChatView.vue',
    'frontend/src/views/BrowserView.vue': ROOT / 'frontend/src/views/BrowserView.vue',
    'frontend/src/App.vue': ROOT / 'frontend/src/App.vue',
    'frontend/src/main.js': ROOT / 'frontend/src/main.js',
}

encoded = {}
for path, fpath in files.items():
    content = fpath.read_text(encoding='utf-8')
    encoded[path] = base64.b64encode(content.encode('utf-8')).decode('ascii')
    print(f"  {path}: {len(content)} chars -> {len(encoded[path])} b64")

# Generate Python deploy script
lines = ['#!/usr/bin/env python3']
lines.append('"""MyAgent Cloud Deploy — python3 deploy_cloud.py"""')
lines.append('import base64, pathlib, subprocess, os, shutil')
lines.append('')
lines.append('# Find project root')
lines.append('ROOT = None')
lines.append('for d in [pathlib.Path("/workspace/template-repos/template-2603/repo")]:')
lines.append('    if (d / "backend" / "main.py").exists(): ROOT = d; break')
lines.append('if not ROOT:')
lines.append('    for d in pathlib.Path("/workspace").glob("*/repo"):')
lines.append('        if (d / "backend" / "main.py").exists(): ROOT = d; break')
lines.append('if not ROOT: print("Project not found!"); exit(1)')
lines.append('print(f"Project: {ROOT}")')
lines.append('os.chdir(ROOT)')
lines.append('')
lines.append('# Try git pull first')
lines.append('r = subprocess.run(["git", "pull", "origin", "main"], capture_output=True)')
lines.append('if r.returncode == 0:')
lines.append('    print("git pull OK, skipping file write")')
lines.append('else:')
lines.append('    print("git pull failed, writing files from embedded b64...")')
lines.append('    FILES = {')
for path, b64 in encoded.items():
    lines.append(f'        {path!r}: {b64!r},')
lines.append('    }')
lines.append('    for path, b64 in FILES.items():')
lines.append('        target = ROOT / path')
lines.append('        target.parent.mkdir(parents=True, exist_ok=True)')
lines.append('        content = base64.b64decode(b64).decode("utf-8")')
lines.append('        target.write_text(content, encoding="utf-8")')
lines.append('        print(f"  Written: {path}")')
lines.append('')
lines.append('# Build frontend')
lines.append('print("Building frontend...")')
lines.append('os.chdir(ROOT / "frontend")')
lines.append('shutil.rmtree(ROOT / "frontend" / "dist", ignore_errors=True)')
lines.append('r = subprocess.run(["npx", "vite", "build"], capture_output=True, text=True)')
lines.append('if r.returncode != 0:')
lines.append('    print(f"BUILD FAILED: {r.stderr[-500:]}"); exit(1)')
lines.append('print("Build OK")')
lines.append('')
lines.append('# Deploy to Nginx')
lines.append('print("Deploying to Nginx...")')
lines.append('TARGET = pathlib.Path("/var/www/myagent")')
lines.append('TARGET.mkdir(parents=True, exist_ok=True)')
lines.append('for item in list(TARGET.iterdir()):')
lines.append('    if item.is_dir(): shutil.rmtree(item)')
lines.append('    else: item.unlink()')
lines.append('for f in (ROOT / "frontend" / "dist").glob("*"):')
lines.append('    dest = TARGET / f.name')
lines.append('    if f.is_dir(): shutil.copytree(f, dest, dirs_exist_ok=True)')
lines.append('    else: shutil.copy2(f, dest)')
lines.append('')
lines.append('print("DEPLOY COMPLETE!")')
lines.append('print("URL: https://rc-83305f57d63fc9d3.radeon.firstdg.ai")')
lines.append('print("Files:", list(TARGET.glob("*")))')

deploy_script = '\n'.join(lines)
output = ROOT / 'deploy_cloud.py'
output.write_text(deploy_script, encoding='utf-8')
print(f"\nGenerated: {output} ({len(deploy_script)} chars, {len(lines)} lines)")
