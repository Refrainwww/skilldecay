# Maintainers' Release Checklist

Before pushing to GitHub:

- [ ] Rotate any API keys that were pasted in chat or local files.
- [ ] Confirm `.env.local.ps1` does not exist or is ignored.
- [ ] Run `rg "sk-[A-Za-z0-9]" -n . --hidden` and confirm no real secrets.
- [ ] Run `python -m compileall -q src benchmarks scripts`.
- [ ] Run the README smoke commands.
- [ ] Replace `your-org/skilldecay` in citation files with the real GitHub URL.
- [ ] Create a fresh git repository from this directory, not from parent `E:\Nenu`.
