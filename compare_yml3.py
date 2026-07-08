import sys

# ============================================================
# SECTION 1: ROBUST YAML PARSER (NO EXTERNAL LIBRARIES)
# ============================================================

def parse_scalar(val: str):
    """Convert a YAML string to Python int, float, bool, None, or string."""
    val = val.strip()
    if val in ('null', '~', 'Null', 'NULL', 'None'):
        return None
    if val in ('true', 'True', 'TRUE', 'yes', 'Yes', 'YES'):
        return True
    if val in ('false', 'False', 'FALSE', 'no', 'No', 'NO'):
        return False
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    try:
        if '.' in val or 'e' in val or 'E' in val:
            return float(val)
        return int(val)
    except ValueError:
        return val

def parse_inline_list(val: str):
    """Parse simple inline lists like '[]' or '[a, b]'."""
    val = val.strip()
    if val == '[]':
        return []
    if val.startswith('[') and val.endswith(']'):
        inner = val[1:-1].strip()
        if not inner:
            return []
        items = [parse_scalar(item.strip()) for item in inner.split(',') if item.strip()]
        return items
    return None

def parse_yaml_document(lines):
    """Parse a single YAML document (list of lines, no '---')."""
    non_empty = [l for l in lines if l.strip() and not l.strip().startswith('#')]
    if not non_empty:
        return {}

    root_is_list = non_empty[0].lstrip().startswith('- ')
    root = [] if root_is_list else {}

    stack = [(-1, root, None)]

    for line in lines:
        line = line.rstrip('\n')
        stripped = line.lstrip(' ')
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(stripped)

        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent_indent, parent_container, parent_key = stack[-1]

        # ---------- List item ----------
        if stripped.startswith('- '):
            val_str = stripped[2:].strip()
            list_container = None

            if isinstance(parent_container, list):
                list_container = parent_container
            elif isinstance(parent_container, dict) and parent_key is not None:
                if parent_key in parent_container:
                    value = parent_container[parent_key]
                    if isinstance(value, list):
                        list_container = value
                    elif isinstance(value, dict) and not value:
                        parent_container[parent_key] = []
                        list_container = parent_container[parent_key]
                        stack[-1] = (parent_indent, list_container, parent_key)
                    else:
                        pass
                else:
                    parent_container[parent_key] = []
                    list_container = parent_container[parent_key]
                    stack[-1] = (parent_indent, list_container, parent_key)
            else:
                if root_is_list and indent == 0 and isinstance(parent_container, list):
                    list_container = parent_container
                else:
                    continue

            if list_container is None:
                continue

            if ':' in val_str:
                key, nested_val = val_str.split(':', 1)
                key = key.strip()
                nested_val = nested_val.strip()
                if nested_val:
                    new_item = {key: parse_scalar(nested_val)}
                    list_container.append(new_item)
                else:
                    new_item = {}
                    list_container.append(new_item)
                    stack.append((indent, new_item, None))
            else:
                list_container.append(parse_scalar(val_str))

        # ---------- Dictionary key ----------
        elif ':' in stripped:
            if stripped.endswith('[]') and ':' in stripped:
                key, list_part = stripped.split(':', 1)
                key = key.strip()
                list_part = list_part.strip()
                parsed_list = parse_inline_list(list_part)
                if parsed_list is not None:
                    if isinstance(parent_container, dict):
                        parent_container[key] = parsed_list
                    elif isinstance(parent_container, list):
                        if len(parent_container) > 0 and isinstance(parent_container[-1], dict):
                            parent_container[-1][key] = parsed_list
                    continue

            if stripped.endswith(':'):
                key = stripped[:-1].strip()
                is_block = True
                val = None
            else:
                key, val_str = stripped.split(':', 1)
                key = key.strip()
                val_str = val_str.strip()
                is_block = (val_str == '')
                val = None if is_block else parse_scalar(val_str)

            if isinstance(parent_container, dict):
                if is_block:
                    parent_container[key] = {}
                    stack.append((indent, parent_container[key], key))
                else:
                    parent_container[key] = val
            elif isinstance(parent_container, list):
                if parent_container and isinstance(parent_container[-1], dict):
                    target_dict = parent_container[-1]
                    if is_block:
                        target_dict[key] = {}
                        stack.append((indent, target_dict[key], key))
                    else:
                        target_dict[key] = val
            else:
                pass
        else:
            pass

    return root

def parse_yaml(text: str):
    """Parse multi‑document YAML (separated by '---') and return list of docs."""
    documents = []
    current_lines = []
    for line in text.splitlines():
        line = line.rstrip('\n')
        if line.strip() == '---':
            if current_lines:
                documents.append(parse_yaml_document(current_lines))
                current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        documents.append(parse_yaml_document(current_lines))
    return documents

# ============================================================
# SECTION 2: FILE LOADER
# ============================================================

def load_yaml(file_path: str):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return parse_yaml(f.read())
    except Exception as e:
        print(f"❌ Error reading file {file_path}: {e}")
        sys.exit(1)

# ============================================================
# SECTION 3: RECURSIVE COMPARISON ENGINE
# ============================================================

def compare_data(ref, other, path=""):
    diffs = []

    if ref == other:
        return diffs

    if type(ref) != type(other):
        diffs.append({
            'path': path,
            'type': 'different',
            'ref_value': ref,
            'other_value': other
        })
        return diffs

    if isinstance(ref, dict) and isinstance(other, dict):
        ref_keys = set(ref.keys())
        other_keys = set(other.keys())

        for key in ref_keys - other_keys:
            diffs.append({
                'path': f"{path}.{key}" if path else key,
                'type': 'missing',
                'ref_value': ref[key],
                'other_value': None
            })

        for key in other_keys - ref_keys:
            diffs.append({
                'path': f"{path}.{key}" if path else key,
                'type': 'extra',
                'ref_value': None,
                'other_value': other[key]
            })

        for key in ref_keys & other_keys:
            new_path = f"{path}.{key}" if path else key
            diffs.extend(compare_data(ref[key], other[key], new_path))

        return diffs

    if isinstance(ref, list) and isinstance(other, list):
        min_len = min(len(ref), len(other))
        for i in range(min_len):
            new_path = f"{path}[{i}]"
            diffs.extend(compare_data(ref[i], other[i], new_path))

        if len(ref) > len(other):
            for i in range(min_len, len(ref)):
                diffs.append({
                    'path': f"{path}[{i}]",
                    'type': 'missing',
                    'ref_value': ref[i],
                    'other_value': None
                })
        elif len(other) > len(ref):
            for i in range(min_len, len(other)):
                diffs.append({
                    'path': f"{path}[{i}]",
                    'type': 'extra',
                    'ref_value': None,
                    'other_value': other[i]
                })
        return diffs

    diffs.append({
        'path': path,
        'type': 'different',
        'ref_value': ref,
        'other_value': other
    })
    return diffs

# ============================================================
# SECTION 4: COLORED OUTPUT WITH ICONS (SORTED & ATOMIC)
# ============================================================

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_diff_report(diffs):
    if not diffs:
        print("✅ No differences found. The two files are semantically identical.")
        return

    # مرتب‌سازی بر اساس اولویت: different > missing > extra
    type_order = {'different': 0, 'missing': 1, 'extra': 2}
    sorted_diffs = sorted(diffs, key=lambda d: type_order.get(d['type'], 3))

    print("🔍 Difference Report (sorted: Different → Missing → Extra):")
    for diff in sorted_diffs:
        path = diff['path']
        typ = diff['type']
        ref_val = diff['ref_value']
        other_val = diff['other_value']

        if typ == 'missing':
            print(f"{RED}  ❌ Missing at path '{path}': Reference value = {repr(ref_val)}, not found in the second file.{RESET}")
        elif typ == 'extra':
            print(f"{GREEN}  ➕ Extra at path '{path}': Extra value = {repr(other_val)}, not found in the reference.{RESET}")
        elif typ == 'different':
            print(f"{YELLOW}  ⚠️  Difference at path '{path}': Reference = {repr(ref_val)}, Second file = {repr(other_val)}{RESET}")

# ============================================================
# SECTION 5: MAIN ENTRY POINT
# ============================================================

def main():
    if len(sys.argv) != 3:
        print("Usage: python compare_yaml.py <reference.yaml> <comparison.yaml>")
        sys.exit(1)

    ref_file = sys.argv[1]
    other_file = sys.argv[2]

    ref_data = load_yaml(ref_file)
    other_data = load_yaml(other_file)

    diffs = compare_data(ref_data, other_data)
    print_diff_report(diffs)

if __name__ == "__main__":
    main()