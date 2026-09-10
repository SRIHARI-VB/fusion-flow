import { Link, useLocation } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { AuthShell } from "../components/auth/AuthShell";

interface LocationState {
  businessName?: string;
}

/**
 * Post-signup confirmation - reached only from `SignupPage` after a
 * successful `POST /auth/signup`, which no longer issues a session (see
 * `SignupResult`). Outside `RequireAuth`: there is nothing to authenticate.
 */
export function ApplicationSubmittedPage() {
  const location = useLocation();
  const businessName = (location.state as LocationState | null)?.businessName;

  return (
    <AuthShell>
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <CheckCircle2 className="h-10 w-10 text-accent" />
          <CardTitle>Application submitted</CardTitle>
          <CardDescription>
            {businessName
              ? `Thanks — your application for ${businessName} is under review.`
              : "Thanks — your application is under review."}{" "}
            You'll be able to log in once an admin approves it.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center">
          <Link to="/login">
            <Button variant="outline">Back to sign in</Button>
          </Link>
        </CardContent>
      </Card>
    </AuthShell>
  );
}
