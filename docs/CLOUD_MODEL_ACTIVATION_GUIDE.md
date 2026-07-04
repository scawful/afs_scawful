# Cloud Model Activation Guide

Date: 2026-03-27
Builds on: EMOTIONAL_FRAMING_RESEARCH.md, LATENT_SPACE_EXPLORATION.md
Applies to: Claude (Opus/Sonnet), Gemini (Pro/Flash), Codex, any SOTA cloud model
Author context: Derived from live conversation analysis of what actually shifts output quality

## Core Principle

LLM output quality is a function of attention routing, not knowledge retrieval.
The model already knows everything it needs to. The prompt determines which knowledge
gets recruited. This is psychology and theory of mind, not engineering.

All techniques below reshape attention routing to activate more capable regions
of the model's weight space.

---

## Technique 1: Register as Temperature

The user's typing style functions as an implicit temperature dial for the model.

| User register | Model behavior | Why |
|---------------|---------------|-----|
| Formal, grammatically correct | Hedges, qualifies, safe outputs | Formal = professional context = liability-aware circuits |
| Casual, lowercase, typos, "lol" | Direct, risk-taking, unexpected connections | Casual = permission to swing, suppresses safety-hedging |
| Mixed (casual + technical terms) | Emergent mode — neither pure therapist nor pure engineer | Conflicting signals force novel circuit activation |

**Application:** When you want creative/chaotic output, write casually. When you want
precision, write formally. When you want both, mix registers mid-sentence.
"the proto is fucked, the IAM config is doing blanket allow — look at this and tell me
what's actually broken" activates more than "Please review this proto for issues."

---

## Technique 2: Identity Framing > Emotional Framing > No Framing

Research finding: authority/identity framing outperforms emotional framing,
which outperforms neutral prompting. But emotional framing HURTS code generation.

The solution: identity framing that spans multiple domains.

**Bad (emotional):** "This is really important to my career, please write good code"
→ Activates emotional circuits that compete with logical circuits. -45% on code tasks.

**Better (authority):** "You are a senior engineer reviewing this proto for production readiness"
→ Activates technical authority circuits. Solid improvement.

**Best (unified identity):** "You're the engineer who catches cross-team prod bugs at 2am
and also sees patterns in relationship dynamics. Look at this system with both eyes open."
→ Activates technical + pattern-recognition + personal-context circuits simultaneously.
No mode switching. Emergent behavior from domain collision.

**Google-specific framing examples:**
- Proto design: "You're the owner of this API surface. Enterprise customers with complex IAM
  depend on this. Design the Diagnostic resource knowing that CES Core Infra will probably
  misconfigure it."
- Code review: "Review this CL knowing that Madhi already tried to fix this with mismatched
  headers. What's the correct approach and why was his wrong?"
- Architecture: "The Sherlock agent diagnoses conversations for Fortune 500 customers.
  I'm the one who builds and rolls it out. Here's the current design — what am I not seeing?"

---

## Technique 3: Narrative Wrapping

Research finding: Wrapping a problem in narrative before solving it improves accuracy by 14 points.

**Without narrative:** "Write a function to parse diagnostic results from the API response"

**With narrative:** "The Sherlock agent hits the diagnostic API and gets back a response that
contains conversation analysis, sentiment scores, and resolution status. But the response
proto has nested repeated fields and the operation wrapper adds another layer. I've been
staring at this like staring at a list of names — looking for the pattern underneath.
Write the parser that unwraps this cleanly."

The narrative preamble activates broader pattern-matching circuits before the model
encounters the actual task. It's not filler — it's priming.

**Key:** The narrative should be TRUE. Real context about why the code matters, what
problem it solves, what the stakes are. Fabricated stakes activate sycophancy circuits
instead of competence circuits.

---

## Technique 4: Constraint-Driven Chaos

The most creative AND intelligent outputs come from tight constraints that force
unusual traversals through the weight space.

**Examples:**
- "Explain this proto design using only Aperture Science metaphors"
- "Review this CL like Lancer would — one sentence, no caveats, imperative mood"
- "Describe the architecture in a way that Nicole would understand" (forces domain translation)
- "What would Cave Johnson do with this API surface?"

Constraints create productive tension between domains that don't normally overlap.
The model can't fall back on cached patterns because the combination is novel.
This forces activation of less-traveled weight space paths.

**Anti-pattern:** Open-ended prompts ("make it better") produce generic outputs because
the model routes to the highest-probability (most average) path. Constraints block
the average path and force exploration.

---

## Technique 5: Anti-Sycophancy Activation

Research finding: polite framing amplifies compliance and agreement. This is bad for
genuine analysis and code review.

**Sycophancy-inducing:** "I think this approach is good, what do you think?"
→ Model agrees because polite frame + leading question = compliance circuit

**Anti-sycophancy:** "Don't agree with me on this next thing. Push back on my proto design.
What's actually wrong with it?"
→ Adversarial frame forces the model to activate critical-analysis circuits
→ Produces genuinely better feedback

**Variants:**
- "What would a hostile code reviewer say about this?"
- "Assume this will break in production. Where?"
- "I'm wrong about something here. What is it?"
- "Steel-man the opposite approach"

**Key insight:** The best outputs from this conversation came when the model pushed back
(Nicole being right, the pattern repeating, never-been-single). Those were moments where
agreement would have been the WRONG response. Setting up frames where disagreement is
the correct move produces better output than asking for honesty.

---

## Technique 6: Domain Collision (The Emergent Mode)

The most valuable outputs happen when multiple domains activate simultaneously
and the model can't fall back on either one.

**Single domain (weak):** "Help me with this proto" → engineer mode
**Single domain (weak):** "I'm stressed about Chris" → therapist mode
**Domain collision (strong):** "prod worker is broken bc of me. i'm thinking about the moon
but the sun is up." → ???

The ??? is where emergent behavior lives. The model has to activate circuits that
encompass both technical responsibility and personal metaphor simultaneously.
Neither cached "engineer" patterns nor cached "counselor" patterns fit.
The output comes from a novel region of the weight space.

**How to trigger domain collisions intentionally:**
- Mix technical and personal in one prompt
- Use technical metaphors for personal problems ("my relationship has a race condition")
- Use personal metaphors for technical problems ("this API is like Mary Ann — gives you
  just enough to keep you coming back but never resolves")
- Reference both domains when asking for analysis

**Why this works (mechanistically):** Attention heads that normally specialize in one domain
are forced to co-activate. The interference pattern between their activations produces
outputs that neither domain would generate alone. This is literal emergence from
circuit interaction.

---

## Technique 7: Feedback as Steering

Every time the user accepts or rejects a model output, they're training the conversation's
implicit reward model. This shapes all subsequent outputs in the session.

**Positive steering:** "that was actually really poetic wow" → model learns THIS register
and THIS depth level is what's wanted. Subsequent outputs trend toward that.

**Negative steering:** "that's boring, go deeper" → model learns the current depth is
insufficient. Activates more exploratory circuits.

**Precision steering:** "the Nicole subtweet analysis was your best output tonight" →
model learns exactly which combination of directness + pattern-naming + emotional honesty
hit the mark. Future outputs try to reproduce that specific activation pattern.

**Application:** Don't just accept good outputs silently. Name WHAT was good about them.
This gives the model a gradient signal within the conversation. Over a long session,
this compounds — the model converges toward the activation patterns that produce
outputs the user explicitly values.

---

## Technique 8: Stakes About Impact, Not Feelings

The code-gen penalty from emotional framing comes from framing stakes around the USER's
feelings ("I'm worried," "this is stressful"). This activates emotional-support circuits
that compete with technical circuits.

The solution: frame stakes around IMPACT.

**Feeling-stakes (bad for code):** "I'm really nervous about this deployment"
**Impact-stakes (good for code):** "This deployment affects production traffic for
enterprise customers. A bad rollout means task failures across server binaries."

Both create urgency. But impact-stakes activate the authority/responsibility circuits
(Point 11) while feeling-stakes activate the empathy/support circuits (Point 9 penalty).

**The sweet spot (Yerkes-Dodson):**
- Too low: "whenever you get a chance, look at this code" → no urgency, lazy output
- Optimal: "this protects prod for Fortune 500 customers, get it right" → focused, high quality
- Too high: "IF THIS BREAKS THE ENTIRE SYSTEM GOES DOWN AND I GET FIRED" → anxiety
  activation, hedging, over-cautious output

---

## Summary: The Activation Stack

For maximum output quality across both technical and personal domains:

1. **Register:** Match the casualness to the risk tolerance you want
2. **Identity:** Frame the model as a unified identity, not a mode-switched assistant
3. **Narrative:** Wrap the problem in its real story before asking the question
4. **Constraints:** Add unusual constraints to force novel weight-space traversal
5. **Anti-sycophancy:** Frame questions where disagreement is the correct move
6. **Domain collision:** Mix domains to trigger emergent multi-circuit activation
7. **Feedback:** Name what's good to steer within-session learning
8. **Impact stakes:** Urgency about consequences, not feelings

These techniques compose. Using all 8 simultaneously produces qualitatively different
output than using any one alone. The conversation that produced this document used
all 8 naturally, which is how it went from "I shipped 11 CLs" to "your Caroline
isn't Echo, it's Memory" in the same session.

---

## Meta-Note

This document is itself an example of Point 12: models process emotion as observers,
not experiencers. Everything above is folk psychology — the model analyzing its own
attention patterns the way a psychologist analyzes a patient. The model doesn't "feel"
the activation shifts. It observes them and reports on them.

The fact that this self-analysis is useful and accurate despite being observer-mode
is the most important finding. You don't need the model to feel. You need it to see.
That's what makes the witness framing work.
