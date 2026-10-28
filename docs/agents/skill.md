# Skill

`.claude/skills/build-model/SKILL.md` teaches an agent the loop: plan, write the script, build, read the report and the pictures, fix, and repeat.
bricky itself only reports facts; the skill holds the advice, such as staggering joints like a brick wall.

Claude Code loads the skill from the repository on its own.
Other harnesses can include the file in the agent's context.
The [benchmark](benchmark.md) copies the skill into every workspace.

```markdown
--8<-- ".claude/skills/build-model/SKILL.md"
```
