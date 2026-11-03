# Fixture host tree

A minimal `/proc`, `/sys` and `/etc` for the machine record tests (RFC-0006 §Machine record): one host with two sockets, two cores each with SMT, two NUMA nodes, an NVMe disk and one GPU at PCI address 0000:17:00.0. The values are invented. Tests that need identifiers to be ignored (a hostname, a MAC address, a GPU UUID) add them to a temporary copy, so none is committed (gate G9).
