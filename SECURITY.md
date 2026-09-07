# Security

Please report a vulnerability privately through this repository's GitHub
Security Advisory page rather than opening a public issue.

Protoke is a local desktop utility, not a network service. It binds only to the
IPv4 loopback address and uses a per-run random token that the interface sends
back on every request. Do not modify it to listen on a LAN or public interface
without adding a full authentication, authorization, origin-validation, and
file-access design.

Transcription and vocal separation are optional and download model weights on
first use. Review downloaded models, checkpoints, and Python packages before
loading them. PyTorch checkpoints may contain pickled Python data and should be
treated as executable content unless they come from a trusted source.
