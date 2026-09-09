import { Toaster as Sonner, toast } from "sonner"

// This used to read `const { theme = "system" } = useTheme()` from
// next-themes. No ThemeProvider was ever mounted, so useTheme returned
// undefined, the default kicked in, and Sonner was handed "system" — which
// makes it follow prefers-color-scheme. The result: every toast rendered as
// a black box floating over a permanently light app, for every user whose
// OS is set to dark.
//
// The app is light-only by design (see design_guidelines.json). There is no
// .dark token block and exactly one `dark:` variant in the entire codebase,
// so "system" could never have been correct. Pinned to light until real dark
// mode exists — which is gated on migrating ~1000 hard-coded palette classes
// onto the semantic tokens, not on this file.
const Toaster = ({
  ...props
}) => {
  return (
    <Sonner
      theme="light"
      className="toaster group"
      toastOptions={{
        classNames: {
          toast:
            "group toast group-[.toaster]:bg-background group-[.toaster]:text-foreground group-[.toaster]:border-border group-[.toaster]:shadow-lg",
          description: "group-[.toast]:text-muted-foreground",
          actionButton:
            "group-[.toast]:bg-primary group-[.toast]:text-primary-foreground",
          cancelButton:
            "group-[.toast]:bg-muted group-[.toast]:text-muted-foreground",
        },
      }}
      {...props} />
  );
}

export { Toaster, toast }
