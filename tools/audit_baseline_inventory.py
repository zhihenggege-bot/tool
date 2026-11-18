"""Inventory tracked C/header/project differences against the general baseline.

Read-only for firmware repositories. Comment/whitespace classification is a
lexical aid, not a proof of behavioral equivalence or specification compliance.
"""
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'fixed-frequency-production'
REPOS = ('PSC330RK-V10-内机', 'PSC316RK-V12-外机')
LEX = re.compile(
    rb'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    rb'|[A-Za-z_][A-Za-z_0-9]*|[0-9]+(?:\.[0-9]+)?|\S')


def git(repo, *args, data=None):
    return subprocess.run(['git', '-C', str(repo), *args], input=data,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          check=True).stdout


def relevant(name):
    lowered = name.lower()
    if any(part in ('.codex-tmp', '_utf8tmp') for part in lowered.split('/')):
        return False
    return Path(name).suffix.lower() in ('.c', '.h', '.uvprojx')


def tokens(content):
    return [match.group() for match in LEX.finditer(content)
            if not match.group().startswith((b'//', b'/*'))]


def read_baseline(repo):
    entries = {}
    for entry in git(repo, 'ls-tree', '-r', '-z', BASE).split(b'\0'):
        if not entry:
            continue
        metadata, raw_name = entry.split(b'\t', 1)
        name = raw_name.decode('utf-8')
        if relevant(name):
            entries[name] = metadata.split()[2]
    object_ids = list(dict.fromkeys(entries.values()))
    output = git(repo, 'cat-file', '--batch', data=b'\n'.join(object_ids) + b'\n')
    position = 0
    contents = {}
    for object_id in object_ids:
        end = output.index(b'\n', position)
        header = output[position:end].split()
        assert header[0] == object_id and header[1] == b'blob'
        size = int(header[2])
        contents[object_id] = output[end + 1:end + 1 + size]
        position = end + 1 + size + 1
    return {name: contents[object_id] for name, object_id in entries.items()}


def project_files(content):
    tree = ET.fromstring(content)
    targets = {}
    for target in tree.findall('.//Target'):
        files = {}
        for file_node in target.findall('./Groups/Group/Files/File'):
            name = file_node.findtext('FilePath', '').replace('\\', '/')
            include = file_node.findtext('.//IncludeInBuild')
            files[name] = {'type': file_node.findtext('FileType'),
                           'include_in_build': include if include is not None else 'inherited'}
        targets[target.findtext('TargetName')] = files
    return targets


def main():
    results = {}
    for repo_name in REPOS:
        repo = ROOT / repo_name
        baseline = read_baseline(repo)
        current = {}
        for raw_name in git(repo, 'ls-files', '-z').split(b'\0'):
            if not raw_name:
                continue
            name = raw_name.decode('utf-8')
            if relevant(name) and (repo / name).is_file():
                current[name] = (repo / name).read_bytes()
        # Untracked C/header/project files can also matter; backups are excluded
        # by their suffix. Inventory them without adding them to either repo.
        for raw_name in git(repo, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
            if raw_name:
                name = raw_name.decode('utf-8')
                if relevant(name) and (repo / name).is_file():
                    current[name] = (repo / name).read_bytes()
        entries = []
        projects = {}
        for name in sorted(set(baseline) | set(current)):
            old, new = baseline.get(name), current.get(name)
            if old is None:
                status = 'added'
            elif new is None:
                status = 'removed'
            elif old == new:
                status = 'same_bytes'
            elif Path(name).suffix.lower() == '.uvprojx':
                status = 'project_changed'
            elif tokens(old) == tokens(new):
                status = 'comments_or_whitespace_only'
            else:
                status = 'tokens_changed'
            entries.append({'path': name, 'classification': status,
                            'baseline_sha256': hashlib.sha256(old).hexdigest() if old is not None else None,
                            'current_sha256': hashlib.sha256(new).hexdigest() if new is not None else None})
            if Path(name).suffix.lower() == '.uvprojx':
                projects[name] = {'baseline': project_files(old) if old else {},
                                  'current': project_files(new) if new else {}}
        counts = {}
        for entry in entries:
            key = entry['classification']
            counts[key] = counts.get(key, 0) + 1
        results[repo_name] = {
            'baseline_commit': git(repo, 'rev-parse', BASE).decode().strip(),
            'current_head': git(repo, 'rev-parse', 'HEAD').decode().strip(),
            'classification_counts': counts, 'files': entries, 'projects': projects,
        }
    target = ROOT / '.codex-tmp/v1017_comparison/baseline_inventory.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, result in results.items():
        print(name, json.dumps(result['classification_counts']))
        for entry in result['files']:
            if entry['classification'] not in ('same_bytes', 'comments_or_whitespace_only'):
                print(' ', entry['classification'], entry['path'])


if __name__ == '__main__':
    main()
