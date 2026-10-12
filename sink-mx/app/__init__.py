"""Lab sink MX server.

A deliberately small SMTP server whose job is to record every observable SMTP
event and to replay a programmable scenario per recipient-class. The lab uses
this to measure how KumoMTA's traffic shaping responds to receiver behavior.

It does NOT:
  - resolve real DNS
  - relay mail
  - accept mail from outside the lab network (loopback-bind in compose)
"""
from .server import main

if __name__ == "__main__":
    main()