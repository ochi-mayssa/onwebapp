
import struct
import sys
import os

def parse_po(filename):
    messages = {}
    current_msgid = []
    current_msgstr = []
    state = 'idle' # idle, msgid, msgstr
    
    with open(filename, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    def process_string(lines_list):
        # Concatenate lines, removing quotes
        res = ""
        for s in lines_list:
            s = s.strip()
            # Handle standard PO comments or empty lines if they got in here
            if not s or s.startswith('#'): continue
            
            if s.startswith('"') and s.endswith('"'):
                s = s[1:-1] # remove outer quotes
                # Handle escapes
                s = s.replace('\\n', '\n')
                s = s.replace('\\t', '\t')
                s = s.replace('\\"', '"')
                s = s.replace('\\\\', '\\')
                res += s
        return res

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
            
        if line.startswith('msgid '):
            if state == 'msgstr':
                # Store previous
                mid = process_string(current_msgid)
                mstr = process_string(current_msgstr)
                messages[mid] = mstr
                current_msgid = []
                current_msgstr = []
            
            state = 'msgid'
            val = line[6:].strip()
            current_msgid.append(val)
            
        elif line.startswith('msgstr '):
            state = 'msgstr'
            val = line[7:].strip()
            current_msgstr.append(val)
            
        elif line.startswith('"'):
            if state == 'msgid':
                current_msgid.append(line)
            elif state == 'msgstr':
                current_msgstr.append(line)
                
    if state == 'msgstr':
        mid = process_string(current_msgid)
        mstr = process_string(current_msgstr)
        messages[mid] = mstr

    return messages

def write_mo(messages, filename):
    # Sort messages by msgid
    # Ensure empty string (header) is included if present
    keys = sorted(messages.keys())
    
    count = len(keys)
    
    ids_encoded = [k.encode('utf-8') + b'\0' for k in keys]
    strs_encoded = [messages[k].encode('utf-8') + b'\0' for k in keys]
    
    # Size of tables
    table_size = count * 8 
    
    # Start of keys data
    # Header is 28 bytes. Two tables of size table_size.
    keys_start_offset = 28 + 2 * table_size
    
    # Start of values data
    values_start_offset = keys_start_offset + sum(len(x) for x in ids_encoded)
    
    output = bytearray()
    
    # Header
    output.extend(struct.pack('<I', 0x950412de)) # Magic
    output.extend(struct.pack('<I', 0))          # Version
    output.extend(struct.pack('<I', count))      # Count
    output.extend(struct.pack('<I', 28))         # Offset of Key Table
    output.extend(struct.pack('<I', 28 + table_size)) # Offset of Value Table
    output.extend(struct.pack('<I', 0))          # Size of hash
    output.extend(struct.pack('<I', 0))          # Offset of hash
    
    # Key Table
    current_off = keys_start_offset
    for b in ids_encoded:
        length = len(b) - 1 # exclude null
        output.extend(struct.pack('<II', length, current_off))
        current_off += len(b)
        
    # Value Table
    current_off = values_start_offset
    for b in strs_encoded:
        length = len(b) - 1 # exclude null
        output.extend(struct.pack('<II', length, current_off))
        current_off += len(b)
        
    # Keys Data
    for b in ids_encoded:
        output.extend(b)
        
    # Values Data
    for b in strs_encoded:
        output.extend(b)
        
    with open(filename, 'wb') as f:
        f.write(output)

if __name__ == '__main__':
    base_dir = os.getcwd()
    po_file = os.path.join(base_dir, 'locale', 'ar', 'LC_MESSAGES', 'django.po')
    mo_file = os.path.join(base_dir, 'locale', 'ar', 'LC_MESSAGES', 'django.mo')
    
    if os.path.exists(po_file):
        print(f"Reading {po_file}...")
        msgs = parse_po(po_file)
        print(f"Parsed {len(msgs)} messages.")
        write_mo(msgs, mo_file)
        print(f"Compiled to {mo_file}")
    else:
        print(f"Error: {po_file} not found")
