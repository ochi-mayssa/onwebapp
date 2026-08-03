
import os
import sys
import struct
import array

def unescape(s):
    return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')

def generate_mo_file(po_file, mo_file):
    with open(po_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    MESSAGES = {}
    current_msgid = None
    current_msgstr = None
    buffer_msgid = []
    buffer_msgstr = []
    state = 'IDLE' # IDLE, MSGID, MSGSTR

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        if line.startswith('msgid '):
            if state == 'MSGSTR':
                # Save previous
                MESSAGES[''.join(buffer_msgid)] = ''.join(buffer_msgstr)
                buffer_msgid = []
                buffer_msgstr = []
            
            state = 'MSGID'
            val = line[6:].strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            buffer_msgid.append(unescape(val))
            
        elif line.startswith('msgstr '):
            state = 'MSGSTR'
            val = line[7:].strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            buffer_msgstr.append(unescape(val))
            
        elif line.startswith('"'):
            val = line.strip()
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            if state == 'MSGID':
                buffer_msgid.append(unescape(val))
            elif state == 'MSGSTR':
                buffer_msgstr.append(unescape(val))

    if state == 'MSGSTR':
        MESSAGES[''.join(buffer_msgid)] = ''.join(buffer_msgstr)

    # Remove empty keys if any (metadata often has empty msgid)
    # Actually metadata is stored with empty msgid, so we keep it.
    
    # Write MO file
    # Magic number: 0x950412de
    # Format version: 0
    # Number of strings
    # Offset of table with original strings
    # Offset of table with translation strings
    # Size of hashing table (0 for now)
    # Offset of hashing table (0 for now)
    
    messages = sorted(MESSAGES.items())
    count = len(messages)
    
    ids = [k.encode('utf-8') for k, v in messages]
    strs = [v.encode('utf-8') for k, v in messages]
    
    # offsets
    keystart = 7 * 4 + 8 * count # Header (28) + 2 tables * (4+4) * count
    valuestart = keystart + sum(len(k) + 1 for k in ids)
    
    koffsets = []
    voffsets = []
    
    # The tables contains (length, offset) pairs
    
    # Calculate offsets
    current_k_off = keystart
    current_v_off = valuestart
    
    for i in range(count):
        klen = len(ids[i])
        vlen = len(strs[i])
        
        koffsets.append(klen)
        koffsets.append(current_k_off)
        current_k_off += klen + 1
        
        voffsets.append(vlen)
        voffsets.append(current_v_off)
        current_v_off += vlen + 1

    output_file = open(mo_file, 'wb')
    
    # Header
    output_file.write(struct.pack('I', 0x950412de)) # Magic
    output_file.write(struct.pack('I', 0)) # Version
    output_file.write(struct.pack('I', count)) # Count
    output_file.write(struct.pack('I', 28)) # Offset of table O
    output_file.write(struct.pack('I', 28 + count * 8)) # Offset of table T
    output_file.write(struct.pack('I', 0)) # Size of hash
    output_file.write(struct.pack('I', 0)) # Offset of hash
    
    # Table O (original strings)
    for i in range(0, len(koffsets), 2):
        output_file.write(struct.pack('II', koffsets[i], koffsets[i+1]))
        
    # Table T (translated strings)
    for i in range(0, len(voffsets), 2):
        output_file.write(struct.pack('II', voffsets[i], voffsets[i+1]))
        
    # Strings
    for s in ids:
        output_file.write(s)
        output_file.write(b'\0')
        
    for s in strs:
        output_file.write(s)
        output_file.write(b'\0')
        
    output_file.close()
    print(f"Compiled {po_file} to {mo_file}")

if __name__ == '__main__':
    base_dir = os.getcwd()
    po_path = os.path.join(base_dir, 'locale', 'ar', 'LC_MESSAGES', 'django.po')
    mo_path = os.path.join(base_dir, 'locale', 'ar', 'LC_MESSAGES', 'django.mo')
    
    if os.path.exists(po_path):
        generate_mo_file(po_path, mo_path)
    else:
        print(f"Error: {po_path} not found")
