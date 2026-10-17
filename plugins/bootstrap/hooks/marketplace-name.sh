# marketplace-name.sh -- sourced by the bootstrap hook scripts; not executed.
#
# bootstrap_marketplace_name <plugin_root>
#
# Prints the marketplace name for a bootstrap plugin root: `name` in
# <plugin_root>/../../.claude-plugin/marketplace.json when that file exists
# (a dev checkout, whose directory name need not match the marketplace), else
# the basename of <plugin_root>/../.. (the cache layout, where the directory
# name IS the marketplace name).
#
# This is a bash port of bootstrap_lib/marketplace_name.py, needed because the
# hooks run before Python exists. Both hook scripts source this one file, and
# tests/bootstrap/test_marketplace_name.py runs it against the Python helper.
#
# A manifest that exists but yields no top-level string name prints the
# basename instead, a warning on stderr, and returns 1. The hook must still
# emit its JSON, so it carries on with the basename; the engine then reads the
# same manifest through the Python helper, raises, and reports the problem
# through its crash path.
bootstrap_marketplace_name() {
    local root="$1" mkt_dir manifest name
    mkt_dir="$(cd "$root/../.." && pwd)"
    manifest="$mkt_dir/.claude-plugin/marketplace.json"
    if [ ! -f "$manifest" ]; then
        basename "$mkt_dir"
        return 0
    fi
    # Top-level "name" only: the file also carries owner.name and one name per
    # plugin. Newlines and tabs become spaces, then awk walks the characters,
    # skipping string bodies, counting {[ and ]} depth, and takes the first
    # depth-1 string key "name" whose value is a plain string.
    name="$(tr '\n\r\t' '   ' < "$manifest" 2>/dev/null | awk '
        {
            s = $0; n = length(s); depth = 0; i = 1
            while (i <= n) {
                c = substr(s, i, 1)
                if (c == "\"") {
                    j = i + 1; str = ""
                    while (j <= n) {
                        d = substr(s, j, 1)
                        if (d == "\\") { str = str substr(s, j, 2); j += 2; continue }
                        if (d == "\"") break
                        str = str d; j++
                    }
                    i = j + 1
                    if (depth == 1 && str == "name") {
                        k = i
                        while (substr(s, k, 1) == " ") k++
                        if (substr(s, k, 1) != ":") continue
                        k++
                        while (substr(s, k, 1) == " ") k++
                        if (substr(s, k, 1) != "\"") exit
                        m = k + 1; val = ""
                        while (m <= n) {
                            e = substr(s, m, 1)
                            if (e == "\\") exit
                            if (e == "\"") break
                            val = val e; m++
                        }
                        if (m > n || val ~ /^ *$/) exit
                        printf "%s", val
                        exit
                    }
                    continue
                }
                if (c == "{" || c == "[") depth++
                else if (c == "}" || c == "]") depth--
                i++
            }
        }')"
    if [ -z "$name" ]; then
        echo "bootstrap: $manifest exists but has no readable top-level string \"name\"; using directory name \"$(basename "$mkt_dir")\" for the hook (the engine will report the manifest)" >&2
        basename "$mkt_dir"
        return 1
    fi
    printf '%s\n' "$name"
}
