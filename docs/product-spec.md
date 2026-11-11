# AI Social

An AI-powered social media SaaS that turns simple inputs into platform-ready posts on autopilot.

## 1. The Landing Page (Public Facing)

This is the front door to your SaaS. It needs to immediately communicate value and drive conversions.

- **Hero Section:** A clean, bold headline (e.g., _"AI-Powered Social Media, on Autopilot"_) with a **"Get Started for Free"** button.
- **Demo/Teaser:** A mock video or looping GIF showing how an image turns into a high-quality video post in three clicks.
- **Feature Grid:** Highlight the core offerings: auto-formatting for different platforms, AI video/image generation, and automated scheduling.
- **Footer:** Standard links (Terms, Privacy, Contact).

## 2. Authentication & Onboarding

Keep the barrier to entry as low as possible.

- **Sign Up / Log In:** A simple, modern form asking for an email and password.
- **Social Connection (Onboarding Step):** A screen featuring large, recognizable buttons (Connect to TikTok, Connect to Instagram, Connect to X) using mock OAuth flows.
- **Success State:** A welcoming confirmation screen that routes them to the Dashboard.

## 3. The Dashboard (User Home)

This should give users an immediate sense of control and overview.

- **Top Navigation:** Links to Dashboard, Create Post, Templates, Calendar, and Settings.
- **Quick Stats:** Visual cards showing _"Posts Scheduled This Week,"_ _"AI Credits Remaining,"_ and _"Connected Accounts."_
- **Upcoming Queue:** A mini-feed of the next 3 to 5 posts scheduled to go out.
- **Primary Call to Action:** A prominent, unmissable **"Create New Post"** button.

## 4. The AI Generation Studio (Create Post Page)

This is the core of your application. To keep it simple, use a step-by-step wizard approach.

| Step | UI Elements & Interaction | Goal |
| --- | --- | --- |
| 1. Choose Template | A visual grid of thumbnail cards representing "System Templates" and "My Templates". | Let the user pick a starting point without seeing the complex AI workflow beneath it. |
| 2. Add Content | Simple text boxes for prompts and a drag-and-drop zone for uploading a "Hero" image. Simple dropdowns for "Video Style" or "Quality". | Gather the data needed to pass to your backend later. |
| 3. Review Output | A mock video player or image gallery showing the "generated" result. Include a "Regenerate" button. | Allow the user to approve the AI's work. |
| 4. Schedule & Format | Checkboxes for target platforms (TikTok, X, Instagram). A date and time picker. | Finalize the post details before pushing to the queue. |

## 5. The Calendar (Scheduling View)

A visual roadmap of the user's content strategy.

- **Monthly/Weekly Toggle:** A standard calendar grid layout.
- **Platform Icons:** Scheduled posts should appear on the calendar days as small chips or cards containing the platform icon (e.g., a small TikTok logo and the time).
- **Drag and Drop:** In the prototype, users should be able to click and drag a scheduled post from a Tuesday to a Thursday to "reschedule" it seamlessly.

## 6. Template Builder (Custom Templates)

For your power users who want more control without using ComfyUI.

- **Configuration Panel:** Input fields to save their preferred default text prompts and negative prompts.
- **Resolution Settings:** Simple dropdowns labeled with plain English like _"Vertical Video (TikTok/Reels)"_ or _"Square (Instagram Post),"_ which your backend will later map to specific resolutions.
- **Save Button:** Allows them to name the template and add it to their personal library for one-click reuse.
