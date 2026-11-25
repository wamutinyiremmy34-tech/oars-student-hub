import { Card } from "@/components/ui/Card";
import { useAuth } from "@/features/auth/auth-context";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card className="space-y-3">
      <h2 className="text-lg font-bold">{title}</h2>
      {children}
    </Card>
  );
}

function Faq({ q, a }: { q: string; a: string }) {
  return (
    <details className="group rounded-control border border-line">
      <summary className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3 font-semibold select-none">
        {q}
        <span className="text-fg-muted transition-transform group-open:rotate-180" aria-hidden>▾</span>
      </summary>
      <p className="border-t border-line px-4 py-3 text-sm text-fg-muted">{a}</p>
    </details>
  );
}

export function HelpPage() {
  const { state } = useAuth();
  const name = state.status === "authenticated" ? state.me.user.full_name.split(" ")[0] : "there";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-extrabold">Help &amp; Support</h1>
        <p className="mt-1 text-fg-muted">Hi {name}, find answers below or get in touch.</p>
      </div>

      <Section title="Frequently asked questions">
        <div className="space-y-2">
          <Faq
            q="How do I find resources for my course?"
            a="Go to Find resources and use the University, Type, or search filters. You can also Browse by course to drill down through your faculty and programme."
          />
          <Faq
            q="What's the difference between Free and Premium resources?"
            a="Free resources are available to all registered users at no cost. Premium resources require a one-time payment before the file is unlocked. The price is shown on the resource page."
          />
          <Faq
            q="How do I download a resource?"
            a="Open a resource's detail page and click Download. If you're not signed in, you'll be asked to sign in first. For premium resources, complete the payment step."
          />
          <Faq
            q="How do I place a print order?"
            a="Go to New print order from the navigation bar. Choose your university and a print shop, upload your documents, configure your printing options, review the price, choose a payment method, and submit."
          />
          <Faq
            q="How do I collect my print order?"
            a="When your order is ready, you'll receive a notification and a pickup code. Show the code at the shop counter to collect your documents."
          />
          <Faq
            q="Can I cancel a print order?"
            a="You can cancel a submitted order before the shop accepts it. Open the order detail page and use the Cancel order option. Once accepted or printing has started, cancellation may no longer be available."
          />
          <Faq
            q="How do I verify my email?"
            a="After registration, we send a verification link to your email address. Click the link in the email. You can still sign in before verifying, but some features may prompt you to verify first."
          />
          <Faq
            q="I forgot my password. What do I do?"
            a="On the sign-in page, click Forgot password. Enter your email and we'll send a reset link. The link expires after 1 hour."
          />
          <Faq
            q="How do I bookmark a resource?"
            a="Click the bookmark icon on any resource card or detail page. Your saved resources are in the Saved section of the navigation."
          />
          <Faq
            q="I uploaded a resource. What happens next?"
            a="After uploading a file, click Submit for review. A reviewer will check it for quality and policy compliance. You'll receive a notification when it's approved or rejected. If rejected, you can edit and re-submit."
          />
        </div>
      </Section>

      <Section title="Contact support">
        <p className="text-sm text-fg-muted">
          If you can't find an answer above, reach out to the OARS support team.
        </p>
        <dl className="grid gap-3 sm:grid-cols-2 text-sm">
          <div>
            <dt className="font-semibold">Email</dt>
            <dd>
              <a href="mailto:support@oarstechnologies.com" className="text-secondary underline hover:no-underline">
                support@oarstechnologies.com
              </a>
            </dd>
          </div>
          <div>
            <dt className="font-semibold">Response time</dt>
            <dd className="text-fg-muted">Within 1 business day</dd>
          </div>
          <div>
            <dt className="font-semibold">Operating hours</dt>
            <dd className="text-fg-muted">Monday – Friday, 8 am – 6 pm EAT</dd>
          </div>
          <div>
            <dt className="font-semibold">System status</dt>
            <dd>
              <a href="/status" className="text-secondary underline hover:no-underline">
                View system status →
              </a>
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="For resource providers">
        <div className="space-y-2">
          <Faq
            q="How do I submit a resource?"
            a="Go to My resources and click New resource. Fill in the details, upload a file, then click Submit for review. Only resources with a file attached can be submitted."
          />
          <Faq
            q="My resource was rejected. What should I do?"
            a="Open the resource and read the reviewer's feedback. Update your resource accordingly, re-upload if needed, and submit again."
          />
          <Faq
            q="Can I edit a submitted resource?"
            a="Once a resource is submitted, it's locked for editing while under review. If it's rejected, it returns to draft and you can edit it again."
          />
        </div>
      </Section>

      <Section title="For printing operators">
        <div className="space-y-2">
          <Faq
            q="How do I see new orders?"
            a="Go to Print queue. New orders appear at the top with a Submitted status. The queue refreshes automatically every 30 seconds."
          />
          <Faq
            q="What does the retention hold do?"
            a="Setting a retention hold prevents the uploaded documents from being automatically deleted after the order completes. This is useful if a customer needs to return or if there's a dispute."
          />
        </div>
      </Section>
    </div>
  );
}
