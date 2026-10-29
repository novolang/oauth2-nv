#!/usr/bin/env bash
# tests/coverage.sh — line coverage of src/, merged over every suite.
#
# Each suite runs under `novo test --cov`; the network suite starts the
# local authorization server itself.  The merged
# report counts a line as covered when any suite ran it.  Exit status 1
# when a suite fails or a line under src/ is not covered.
set -u
cd "$(dirname "$0")/.."
rm -rf _novo
status=0
for s in oautherr oauthtoken oauthmsg oauthdisc oauthoidc oauthoidc_signed oauthflow; do
    novo test "tests/${s}_tests.nv" --cov --report=lcov >"/tmp/oauth2-nv-cov-$s.log" 2>&1 \
        || { echo "FAIL $s"; tail -20 "/tmp/oauth2-nv-cov-$s.log"; status=1; }
done
novo test tests/oauthnet_tests.nv --cov --report=lcov >/tmp/oauth2-nv-cov-net.log 2>&1 \
    || { echo "FAIL oauthnet"; tail -20 /tmp/oauth2-nv-cov-net.log; status=1; }
python3 -I - "$PWD" <<'P' || status=1
import glob, os, sys
root = sys.argv[1]
cov = {}
for f in glob.glob(os.path.join(root, '_novo', '*.lcov.info')):
    cur = None
    for l in open(f):
        l = l.strip()
        if l.startswith('SF:'):
            cur = os.path.abspath(l[3:])
        elif l.startswith('DA:') and cur and cur.startswith(os.path.join(root, 'src') + os.sep):
            n, c = l[3:].split(',')[:2]
            d = cov.setdefault(cur, {})
            d[int(n)] = max(d.get(int(n), 0), int(c))
def excused(path, n):
    # `// cov: skip — reason` directly above the line, or above the
    # line that opens the deeper block this line sits in.
    lines = open(path).read().split('\n')
    indent = len(lines[n - 1]) - len(lines[n - 1].lstrip())
    i = n - 2
    while i >= 0:
        t = lines[i].strip()
        ind = len(lines[i]) - len(lines[i].lstrip())
        if t.startswith('// cov: skip') and ind <= indent:
            return True
        if t and not t.startswith('//') and ind < indent:
            return False
        if t and not t.startswith('//') and ind == indent and i < n - 2:
            return False
        i -= 1
    return False

total = hit = skipped = 0
for f, d in sorted(cov.items()):
    for n in [n for n, c in d.items() if c == 0 and excused(f, n)]:
        del d[n]; skipped += 1
    miss = sorted(n for n, c in d.items() if c == 0)
    total += len(d); hit += len(d) - len(miss)
    print("%-16s %4d / %-4d%s" % (os.path.basename(f), len(d) - len(miss), len(d), "  missed " + str(miss) if miss else ""))
print("TOTAL            %d / %d  (%.1f%%), %d line(s) excused by `cov: skip`" % (hit, total, 100.0 * hit / total if total else 0, skipped))
sys.exit(0 if hit == total and total > 0 else 1)
P
rm -rf _novo
exit $status
