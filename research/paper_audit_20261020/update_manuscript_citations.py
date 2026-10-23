import pathlib

md_path = pathlib.Path('research/paper_audit_20261020/FINAL_DEMO_PAPER.md')
src = md_path.read_text(encoding='utf-8')

# Target 1: Pure op-based CRDTs [24]
t1_old = 'During sync, incoming increments are applied once and registered in the change log as stable receipts, preventing duplicate replay.'
t1_new = 'During sync, incoming increments are applied once and registered in the change log as stable receipts, preventing duplicate replay. This design incorporates principles of pure operation-based CRDTs [24], which transmit compact operation messages rather than full state, bounding bandwidth consumption across resource-constrained local replicas.'

# Target 2: Remove-Win [25]
t2_old = 'When concurrent operations diverge between row update and row deletion, SemanticSync detects an `UPDATE_DELETE` conflict. I implemented configurable tombstone resolution strategies:'
t2_new = 'When concurrent operations diverge between row update and row deletion, SemanticSync detects an `UPDATE_DELETE` conflict. Concurrent update-remove conflicts present a classic challenge in replicated systems, as analyzed by Zhang et al. in the remove-win design framework [25]. I implemented configurable tombstone resolution strategies:'

# Target 3: Crust [26]
t3_old = '2. **Explicit-INCREMENT Evaluation Matrix:** A comprehensive 90-trial matrix auditing dedicated operation-based additive increments across nine configurations (10 independent seeds per cell).'
t3_new = '2. **Explicit-INCREMENT Evaluation Matrix:** A comprehensive 90-trial matrix auditing dedicated operation-based additive increments across nine configurations (10 independent seeds per cell), adopting rigorous benchmarking and validation methodologies recommended for replicated data types [26].'

# Target 4: Tomter 2021 [23]
t4_old = '- **Relational CRDTs:** Synql [14] uses CRDT compositions to manage relational constraints, and CRDV [15] introduces replicated relational views. Thomassen and Yu [16] explore updatable views in eventually consistent databases, while Lopes [17] developed Antidote SQL. Commercial local-first systems like ElectricSQL [13] and `cr-sqlite` [12] offer SQLite replication. Riffle [22] addresses client relational state management. Unlike systems relying on custom virtual tables or whole-database CRDT conversions, SemanticSync provides policy assignment over unmodified SQLite tables.'
t4_new = '- **Relational CRDTs and SQLite Augmentation:** Synql [14] uses CRDT compositions to manage relational constraints, and CRDV [15] introduces replicated relational views. Thomassen and Yu [16] explore updatable views in eventually consistent databases, while Lopes [17] developed Antidote SQL. In adjacent work on SQLite, Tomter and Yu [23] augmented standard SQLite with conflict-free replicated relations using auxiliary delta tables and SQL triggers without modifying engine internals. Commercial local-first systems like ElectricSQL [13] and `cr-sqlite` [12] offer SQLite replication, and Riffle [22] provides reactive client relational queries. Unlike approaches relying on custom virtual tables or whole-database CRDT conversions, SemanticSync provides policy assignment directly over unmodified SQLite tables.'

# References additions
new_refs = '''23. I. T. Tomter and W. Yu, "Augmenting SQLite for Local-First Software," in *Advances in Databases and Information Systems (ADBIS 2021 Short Papers)*, CCIS 1450, pp. 233-243, 2021. DOI: 10.1007/978-3-030-85082-1_22.
24. J. Bauwens and E. Gonzalez Boix, "Nested Pure Operation-Based CRDTs," in *Proc. ECOOP 2023*, LIPIcs 263, Art. 2, pp. 2:1-2:26, 2023. DOI: 10.4230/LIPIcs.ECOOP.2023.2.
25. Y. Zhang, H. Wei, and Y. Huang, "Remove-Win: A Design Framework for Conflict-Free Replicated Data Types," in *Proc. ICPADS 2021*, pp. 597-604, 2021. DOI: 10.1109/ICPADS53394.2021.00081.
26. Y. Zhu and J. Ma, "Crust: A Modular Framework for Conflict-Free Replicated Data Types (CRDTs) Development, Validation, and Benchmarking," *IEEE Access*, vol. 13, pp. 83870-83882, 2025. DOI: 10.1109/ACCESS.2025.3568925.
'''

assert t1_old in src, 't1 not found'
assert t2_old in src, 't2 not found'
assert t3_old in src, 't3 not found'
assert t4_old in src, 't4 not found'

src = src.replace(t1_old, t1_new)
src = src.replace(t2_old, t2_new)
src = src.replace(t3_old, t3_new)
src = src.replace(t4_old, t4_new)

# Append new refs to REFERENCES section
src = src.strip() + '\n' + new_refs

md_path.write_text(src, encoding='utf-8')
print('Updated FINAL_DEMO_PAPER.md successfully! Length:', len(src))
