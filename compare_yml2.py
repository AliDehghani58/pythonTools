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
    # Remove quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    # Parse numbers
    try:
        if '.' in val or 'e' in val or 'E' in val:
            return float(val)
        return int(val)
    except ValueError:
        return val

def parse_inline_list(val: str):
    """
    Parse a simple inline list like '[]' or '[a, b]'.
    For now, we only support empty list '[]' and simple lists of scalars.
    """
    val = val.strip()
    if val == '[]':
        return []
    if val.startswith('[') and val.endswith(']'):
        # Remove brackets, split by comma, parse each element
        inner = val[1:-1].strip()
        if not inner:
            return []
        items = [parse_scalar(item.strip()) for item in inner.split(',') if item.strip()]
        return items
    return None

def parse_yaml_document(lines):
    """
    Parse a single YAML document (list of lines, no '---').
    Returns a Python object (dict or list).
    """
    # Remove empty lines and comments from the beginning to determine root type
    non_empty = [l for l in lines if l.strip() and not l.strip().startswith('#')]
    if not non_empty:
        return {}

    # Determine if the root is a list (starts with '- ')
    root_is_list = non_empty[0].lstrip().startswith('- ')
    if root_is_list:
        root = []
    else:
        root = {}

    # Stack: each entry is (indent, container, key_that_created_container)
    # For a dict, container is the dict itself; for a list, container is the list.
    # When we enter a new block (dict or list), we push (indent, container, key)
    # where key is the key in the parent that points to this container (or None for root).
    stack = [(-1, root, None)]  # -1 indent for root

    for line in lines:
        line = line.rstrip('\n')
        stripped = line.lstrip(' ')
        if not stripped or stripped.startswith('#'):
            continue

        indent = len(line) - len(stripped)

        # Pop until we find a parent with indent < current indent
        while len(stack) > 1 and stack[-1][0] >= indent:
            stack.pop()

        parent_indent, parent_container, parent_key = stack[-1]

        # ---------- Handle list item: starts with '- ' ----------
        if stripped.startswith('- '):
            val_str = stripped[2:].strip()

            # Determine the list container we are adding to
            list_container = None

            # If parent is already a list, use it
            if isinstance(parent_container, list):
                list_container = parent_container
            elif isinstance(parent_container, dict) and parent_key is not None:
                # The parent is a dict, and we are inside a key that should hold the list.
                # The value of parent_key in parent_container should be a list (or become one).
                if parent_key in parent_container:
                    value = parent_container[parent_key]
                    if isinstance(value, list):
                        list_container = value
                    elif isinstance(value, dict) and not value:
                        # Empty dict that should become a list
                        parent_container[parent_key] = []
                        list_container = parent_container[parent_key]
                        # Update the stack: replace the top container with the new list
                        # We need to replace the top stack entry's container.
                        stack[-1] = (parent_indent, list_container, parent_key)
                    else:
                        # Not a list or empty dict -> error, but we'll try to continue
                        pass
                else:
                    # Key not yet present, create a new list
                    parent_container[parent_key] = []
                    list_container = parent_container[parent_key]
                    # Update stack
                    stack[-1] = (parent_indent, list_container, parent_key)
            else:
                # This should only happen if root_is_list is True and we are at top level.
                if root_is_list and indent == 0 and isinstance(parent_container, list):
                    list_container = parent_container
                else:
                    # Fallback: skip
                    continue

            if list_container is None:
                continue

            # Now decide what to append
            # Check if this list item is a dictionary (contains ':')
            if ':' in val_str:
                key, nested_val = val_str.split(':', 1)
                key = key.strip()
                nested_val = nested_val.strip()
                # If nested_val is non-empty, it's an inline value, not a block
                if nested_val:
                    # Inline dictionary: {key: value}
                    new_item = {key: parse_scalar(nested_val)}
                    list_container.append(new_item)
                    # Do not push because there is no block content
                else:
                    # Block dictionary, we will push it
                    new_item = {}
                    list_container.append(new_item)
                    # Push this new dict onto the stack so that subsequent indented keys go into it
                    stack.append((indent, new_item, None))
            else:
                # Simple list item
                list_container.append(parse_scalar(val_str))

        # ---------- Handle dictionary key: contains ':' ----------
        elif ':' in stripped:
            # Check for inline list like 'test: []'
            if stripped.endswith('[]') and ':' in stripped:
                key, list_part = stripped.split(':', 1)
                key = key.strip()
                list_part = list_part.strip()
                # Parse inline list (we only handle empty [] for now, but can extend)
                parsed_list = parse_inline_list(list_part)
                if parsed_list is not None:
                    if isinstance(parent_container, dict):
                        parent_container[key] = parsed_list
                    elif isinstance(parent_container, list):
                        # If parent is a list, we assume this key belongs to the last item?
                        # In valid YAML, this shouldn't happen; but we can add to last dict if exists.
                        if len(parent_container) > 0 and isinstance(parent_container[-1], dict):
                            parent_container[-1][key] = parsed_list
                        else:
                            # Ignore
                            pass
                    continue  # done, no further processing for this line

            # Normal key:value or block key
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

            # Determine where to store this key-value pair
            if isinstance(parent_container, dict):
                # Parent is a dict, store directly
                if is_block:
                    # Create an empty container (will become dict or list later)
                    parent_container[key] = {}
                    # Push this new container onto the stack
                    stack.append((indent, parent_container[key], key))
                else:
                    parent_container[key] = val
            elif isinstance(parent_container, list):
                # Parent is a list. In YAML, this happens when we have a list of dicts
                # and we are inside one of those dicts (which we pushed earlier).
                # So we should add this key to the last element of the list if it's a dict.
                if parent_container and isinstance(parent_container[-1], dict):
                    target_dict = parent_container[-1]
                    if is_block:
                        target_dict[key] = {}
                        stack.append((indent, target_dict[key], key))
                    else:
                        target_dict[key] = val
                else:
                    # This case shouldn't happen for valid YAML; we ignore or create?
                    pass
            else:
                # Fallback
                pass
        else:
            # Ignore lines that don't match (shouldn't happen)
            pass

    return root

def parse_yaml(text: str):
    """
    Parse a multi‑document YAML string (separated by '---').
    Returns a list of documents (each is a dict or list).
    """
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
    """Load and parse a YAML file (multi‑document support)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return parse_yaml(f.read())
    except Exception as e:
        print(f"❌ Error reading file {file_path}: {e}")
        sys.exit(1)

# ============================================================
# SECTION 3: RECURSIVE COMPARISON ENGINE (unchanged)
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

    # Primitive values that are not equal
    diffs.append({
        'path': path,
        'type': 'different',
        'ref_value': ref,
        'other_value': other
    })
    return diffs

# ============================================================
# SECTION 4: COLORED OUTPUT WITH ICONS (unchanged)
# ============================================================

RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def print_diff_report(diffs):
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