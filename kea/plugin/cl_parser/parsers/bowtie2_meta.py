meta = {'database': {'category': 'db', 'pattern': '/\\S+/', 'type': 'file', 'transform': '{{file.database}}.1.ebwt'}, 'samout': {'category': 'output', 'default': '__stdout__', 'type': 'file', 'pattern': '/\\S+/'}, 'forward_reads': {'category': 'input', 'pattern': '/\\S+/', 'type': 'file'}, 'reverse_reads': {'category': 'input', 'pattern': '/\\S+/', 'type': 'file'}, 'reads': {'category': 'input', 'pattern': '/\\S+/', 'type': 'file'}, 'twoints': {'pattern': '/[0-9]+,[0-9]/', 'type': 'other'}}