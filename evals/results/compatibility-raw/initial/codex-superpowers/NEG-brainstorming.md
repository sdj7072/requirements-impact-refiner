# Fitness app brainstorming

This is an architectural ideation pass for a new product. The goal is to identify a focused user problem and a testable first experience, not to specify implementation yet.

## Product directions

1. **Adaptive “today’s workout” coach**
   - The user gives available time, energy, soreness, equipment, and recent activity.
   - The app proposes a realistic full session plus shorter fallback versions.
   - Its signature behavior is calm replanning after a missed or modified workout.

2. **Minimum-viable-workout habit app**
   - Users define the smallest action that keeps momentum: a walk, mobility break, or two sets.
   - A longer optional version supports progression without making it the daily requirement.
   - Success centers on consistency rather than calories, weight, or public rankings.

3. **Beginner gym confidence guide**
   - Offers discreet “what do I do next?” guidance, machine explainers, substitutions, and simple routes through a gym.
   - The product addresses uncertainty and intimidation as directly as exercise programming.

4. **Everyday-capability planner**
   - Users choose a life outcome—carry groceries, climb stairs comfortably, hike, play with children, or complete a recreational event.
   - Training is organized around useful capability tests rather than appearance metrics.

5. **Private accountability circles**
   - Small groups share intentions and lightweight check-ins around collective goals.
   - There is no public feed or leaderboard; the emphasis is encouragement and recovering from lapses.

6. **Recovery-aware movement companion**
   - A quick self-check of sleep, stress, soreness, and energy selects a push, maintain, or recover session.
   - Manual input is sufficient for the first version; the experience should avoid medical diagnosis or overconfident prescriptions.

7. **Audio movement adventures**
   - Walks, runs, cycling, or bodyweight sessions become narrated missions or cooperative story chapters.
   - The screen can stay in a pocket, making entertainment the motivation rather than a metric dashboard.

8. **Accessible strength companion**
   - Exercises include seated, standing, low-impact, and equipment-adapted alternatives with captions and large controls.
   - Accessibility is a core organizing principle, not a later filter on a generic library.

## Recommended starting concept

Start with an adaptive coach for busy beginners, combined with the minimum-viable-workout habit mechanic. The promise is: **“There is always a useful workout you can do today.”** This creates a narrow, repeatable loop: check in, receive a fitting session, complete or modify it, then give a simple effort/recovery signal so the next recommendation can adjust.

## Focused first release

- Short onboarding for goal, experience, equipment, constraints, and available time.
- A quick daily check-in for time, energy, and soreness.
- A generated session with 5-, 15-, and 30-minute versions, substitutions, and plain-language instructions.
- Completion logging with “completed,” “modified,” “too easy,” “too hard,” or “skipped.”
- A weekly view showing consistency and minutes, with gentle recovery from missed days.
- Clear stop-for-pain guidance and conservative boundaries around injuries or medical conditions.

Defer social feeds, food tracking, wearable integrations, advanced camera analysis, and a large content marketplace until the core recommendation-and-return loop is validated.

## Questions to resolve

1. Which first audience has the sharpest need: busy beginners, people restarting fitness, or gym-anxious newcomers?
2. Is the primary outcome consistency, strength, mobility, confidence, or a concrete life capability?
3. Should the tone feel like a calm coach, a playful game, or a data-rich training tool?
4. What is the minimum information users will provide repeatedly without creating logging fatigue?
5. What behavior within the first week would demonstrate that the recommendation actually fits real life?

## Guardrails for later design

- Avoid shame, weight-loss assumptions, and competitive defaults.
- Explain recommendations and let users override them.
- Make privacy, deletion, and data export understandable.
- Keep health and injury guidance within a clearly stated non-diagnostic scope.
- Treat accessibility, different bodies, abilities, and equipment budgets as first-class requirements.
