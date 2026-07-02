import sys

# ============================================================
# SECTION 1: CUSTOM YAML PARSER (Handwritten, no libraries)
# ============================================================

def parse_scalar(val: str):
    """Convert a string value to appropriate Python data type (int, float, bool, None, or str)."""
    val = val.strip()
    if val in ('null', '~', 'Null', 'NULL', 'None'):
        return None
    if val in ('true', 'True', 'TRUE', 'yes', 'Yes', 'YES'):
        return True
    if val in ('false', 'False', 'FALSE', 'no', 'No', 'NO'):
        return False
    # Remove surrounding quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    # Detect numbers (int or float)
    try:
        if '.' in val or 'e' in val or 'E' in val:
            return float(val)
        return int(val)
    except ValueError:
        return val

def parse_yaml(text: str):
    """
    A simple YAML parser based on indentation.
    Supports nested dictionaries, lists, and primitive types.
    """
    lines = text.splitlines()
    root = {}
    # Stack: (indent_level, container, last_key)
    stack = [(0, root, None)]

    for line in lines:
        line = line.rstrip('\n')
        stripped = line.lstrip(' ')
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(stripped)

        # Pop stack until we find the correct parent based on indentation
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent_indent, parent_container, parent_last_key = stack[-1]

        # ---------- Handle list items (lines starting with '- ') ----------
        if stripped.startswith('- '):
            val_str = stripped[2:].strip()

            list_container = None

            # Special case: root-level list
            if parent_container is root and parent_last_key is None:
                if not root:
                    root['_root_list'] = []
                list_container = root['_root_list']
            elif isinstance(parent_container, list):
                list_container = parent_container
            elif isinstance(parent_container, dict) and parent_last_key is not None:
                if parent_last_key not in parent_container:
                    parent_container[parent_last_key] = []
                elif isinstance(parent_container[parent_last_key], dict) and not parent_container[parent_last_key]:
                    parent_container[parent_last_key] = []
                list_container = parent_container[parent_last_key]

            if list_container is None:
                continue

            # Determine the type of list item
            if not val_str:  # e.g., '- ' and value comes on the next line
                new_item = {}
                list_container.append(new_item)
                stack.append((indent, new_item, None))
            elif ':' in val_str:  # e.g., '- name: Ali'
                key, nested_val = val_str.split(':', 1)
                key = key.strip()
                nested_val = nested_val.strip()
                new_dict = {}
                if nested_val:
                    new_dict[key] = parse_scalar(nested_val)
                list_container.append(new_dict)
                if not nested_val:
                    stack.append((indent, new_dict, key))
            else:  # Simple value, e.g., '- apple'
                list_container.append(parse_scalar(val_str))

        # ---------- Handle dictionary keys (lines containing ':') ----------
        elif stripped.endswith(':') or ':' in stripped:
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

            # If parent is a list (list of dictionaries)
            if isinstance(parent_container, list):
                new_dict = {}
                if not is_block and val is not None:
                    new_dict[key] = val
                parent_container.append(new_dict)
                if is_block:
                    stack.append((indent, new_dict, key))
            else:
                # Parent is a dictionary
                if is_block:
                    parent_container[key] = {}
                    stack.append((indent, parent_container[key], key))
                else:
                    parent_container[key] = val
        else:
            # Unknown line format - skip
            pass

    # If root was converted to a list, extract it
    if '_root_list' in root and len(root) == 1:
        return root['_root_list']
    return root

# ============================================================
# SECTION 2: FILE LOADER
# ============================================================

def load_yaml(file_path: str):
    """Load a YAML file from disk and parse it using the custom parser."""
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
    """
    Recursively compare two data structures (dicts, lists, primitives).
    Returns a list of differences.
    """
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

        # Keys present in reference but missing in the other
        for key in ref_keys - other_keys:
            diffs.append({
                'path': f"{path}.{key}" if path else key,
                'type': 'missing',
                'ref_value': ref[key],
                'other_value': None
            })

        # Keys present in the other but not in reference
        for key in other_keys - ref_keys:
            diffs.append({
                'path': f"{path}.{key}" if path else key,
                'type': 'extra',
                'ref_value': None,
                'other_value': other[key]
            })

        # Common keys: recurse
        for key in ref_keys & other_keys:
            new_path = f"{path}.{key}" if path else key
            diffs.extend(compare_data(ref[key], other[key], new_path))

        return diffs

    if isinstance(ref, list) and isinstance(other, list):
        min_len = min(len(ref), len(other))
        # Compare common indices
        for i in range(min_len):
            new_path = f"{path}[{i}]"
            diffs.extend(compare_data(ref[i], other[i], new_path))

        # Reference has more elements
        if len(ref) > len(other):
            for i in range(min_len, len(ref)):
                diffs.append({
                    'path': f"{path}[{i}]",
                    'type': 'missing',
                    'ref_value': ref[i],
                    'other_value': None
                })
        # Other has more elements
        elif len(other) > len(ref):
            for i in range(min_len, len(other)):
                diffs.append({
                    'path': f"{path}[{i}]",
                    'type': 'extra',
                    'ref_value': None,
                    'other_value': other[i]
                })
        return diffs

    # Primitive values (int, str, float, bool, None) that are not equal
    diffs.append({
        'path': path,
        'type': 'different',
        'ref_value': ref,
        'other_value': other
    })
    return diffs

# ============================================================
# SECTION 4: COLORED OUTPUT WITH ICONS (ANSI + Unicode)
# ============================================================

# ANSI color codes for terminal output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_diff_report(diffs):
    """Print a beautifully formatted, colored report of all differences."""
    if not diffs:
        print("✅ No differences found. The two files are semantically identical.")
        return

    print("🔍 Difference Report:")
    for diff in diffs:
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