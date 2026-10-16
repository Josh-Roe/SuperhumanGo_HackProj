# Hackathon brief

**MTC x Grammarly: Agents in Action** — *Build your next move. Create AI-powered experiences with Superhuman Go or Grammarly agents.*

Sources: [overview](https://mtc-x-grammarly.devpost.com/), [rules](https://mtc-x-grammarly.devpost.com/rules), and [resources](https://mtc-x-grammarly.devpost.com/resources), read October 16, 2026. Check [Updates](https://mtc-x-grammarly.devpost.com/updates) and the organizer Slack channel for changes.

## At a glance

| | |
| --- | --- |
| Host | MTC Berkeley (Muslim Tech Collaborative), sponsored by Grammarly |
| When | **October 16, 2026, 1:00–10:00 PM Pacific**, in person |
| Where | Berkeley, CA (venue shared with accepted participants) |
| Submission deadline | **8:00 PM Pacific on Devpost** ([manage submission](https://devpost.com/submit-to/31728-mtc-x-grammarly-agents-in-action/manage/submissions)) |
| Who | College students in the US who have reached the age of majority; teams of 2–4 |
| Access | Invite only: attendance requires registration approval, and Devpost registration alone does not confirm it |
| Prizes | 1 non-cash prize, 3 winners; details to be announced |
| Themes | Communication, Machine Learning/AI, Productivity |

The event has a Scrabble-inspired theme: assemble your team, choose your track, and make your move.

## Objective

Build a working prototype with **Superhuman Go or Grammarly agents as a central part of the experience**. Other tools, APIs, and frameworks may be combined with them. The prototype should demonstrate its core functionality and make clear how the agent contributes to the experience.

Choose one primary track:

| Track | Brief | Focus |
| --- | --- | --- |
| Productivity | Reimagine how people work, learn, and create. Explore how agents can help people move ideas forward, collaborate in new ways, or approach familiar challenges differently. | Automate repetitive tasks or improve an existing workflow |
| Inclusion & Accessibility | Explore how technology can open more possibilities for more people. Consider the different ways people communicate, navigate information, and experience the world. | Reduce barriers to communication, learning, work, or access to information |
| Wildcard | Follow an idea that doesn't fit neatly into a category, or that brings several together: useful, playful, experimental, or unexpected. | Explore a creative or unexpected use of agents |

The team has not selected an idea or track yet. The approved scaffold uses React/TypeScript, Python APIs/ML, and a Superhuman Go connector. Those tools support the prototype. The agent's contribution must still be demonstrated in the chosen user workflow.

## Schedule

All times are Pacific (`America/Los_Angeles`).

| Time | Event |
| --- | --- |
| 1:00 PM | Check-in |
| 1:30 PM | Opening ceremony and Grammarly keynote |
| 2:30 PM | Hacking begins |
| 4:00–5:00 PM | Recruiting hour with Grammarly |
| 8:00 PM | Hacking ends; Devpost submissions due |
| 8:45 PM | Finalists announced |
| 8:50–9:30 PM | Finalist presentations |
| 9:30–10:00 PM | Awards ceremony |
| 10:00 PM | Event concludes |

Preparation before the event is encouraged, but competition work should begin when the hacking period opens. That is why the existing scaffold must be disclosed (see below).

## Setup on event day

1. Install the [Grammarly Chrome extension](https://www.grammarly.com/browser/chrome).
2. Redeem the Grammarly voucher handed out on event day. It gives access to Superhuman Go. Vouchers and swag go only to participants attending in person.
3. Turn on Superhuman Go in the extension after redeeming the voucher.
4. Bring a laptop and charger, and make sure you can log in to Devpost.

Then follow [Superhuman setup](SUPERHUMAN.md) to connect our hosted MCP tools.

## Submission requirements

Due on Devpost by **8:00 PM Pacific**:

- [ ] Project name and selected primary track
- [ ] Project description: the problem, intended users, and how the solution works
- [ ] Agent integration: how Superhuman Go or Grammarly agents are used
- [ ] Demo: short video showing the prototype's core functionality
- [ ] Project links: source repository and a working demo link if available, plus setup instructions so judges can review the project
- [ ] Team members: everyone who contributed
- [ ] Tools and credits: technologies used, plus disclosure of any pre-existing code, templates, or assets
- [ ] All links accessible to judges, with API keys, credentials, and private data removed

Finalists must be ready to give a **2-minute live pitch and demo**. This setup does not submit anything to Devpost.

## Judging

No weights are published.

| Criterion | Question |
| --- | --- |
| Impact & Usefulness | Does the project solve a meaningful problem and provide clear value to its intended users? |
| Agent Integration | How effectively does the project use Superhuman Go or Grammarly agents as a central part of the experience? |
| Technical Execution | Does the prototype work and demonstrate its core functionality? How well are its tools and components integrated? |
| Creativity & Innovation | Does the project introduce an original idea, an unexpected use of agents, or a fresh approach to an existing problem? |
| User Experience | Is the project intuitive, clear, and appropriate for its intended audience? |

Judges: Rameen Rauf, Shrey Verma, Suman Shil, Vivek Venkatram, Victoria Okhrimchuk.

## Learning resources

- Getting started with Superhuman Go: [video](https://grammarly.wistia.com/s/fw5io1iiw1cfdag) and [written walkthrough](https://connect.superhuman.com/t/getting-started-with-go/61662)
- [Superhuman Go app guide](https://help.superhuman.com/hc/en-us/articles/47423940514317-Superhuman-Go-app-guide)
- [Superhuman Go online course](https://academy.superhuman.com/getting-started-with-superhuman-go-for-education/573109/scorm/3nwsko9ykzj0c)
- [Inspiration video from Noah](https://youtu.be/-OAJ_ze1sVA), who is also speaking at the event

For ideas, organizers suggest starting from a problem you have experienced yourself: a repetitive workflow an agent could simplify (Productivity), a barrier to communicating, learning, or working (Inclusion & Accessibility), or an unexpected experience built with agents (Wildcard).

## Support

- The `mtc-x-grammarly` channel in the [MTC Berkeley Slack](https://join.slack.com/t/mtcberkeley/shared_invite/zt-45bo6l0ms-rkRrc4UB5dSRSF5YqQrdUQ) carries updates, team matching, and support. Message an organizer to be added to the channel.
- During the event, ask an MTC organizer for help with logistics or to reach technical support. For private concerns, message Heba Alazzeh on Slack or talk to an organizer in person.

By attending, participants consent to being photographed and recorded for MTC Berkeley and partner promotional materials.

## Existing work disclosure

The repository began with Git attributes, repository documentation, ignore rules, and collaboration templates. The next setup phase added a React/TypeScript frontend, a Python API and MCP scaffold, a Superhuman Go connector, optional ONNX/C++ inference support, and development/deployment tooling. Disclose that scaffold and any reused code, templates, or assets in the submission's tools and credits. Keep scaffold work distinguishable from the eventual hackathon product features.

See [the architecture](ARCHITECTURE.md) for the technical starting point and [the presentation brief](PRESENTATION.md) for pitch and Canva preparation. Actual Go installation, external credentials, model training, VPS deployment, and submission remain separate tasks.
