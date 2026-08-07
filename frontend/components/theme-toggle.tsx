"use client";

import { Moon, Sun } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);

  const toggle = () => {
    setDark(!dark);
  };

  return (
    <Button variant="ghost" size="icon" onClick={toggle}>
      {dark ? <Moon className="size-4" /> : <Sun className="size-4" />}
    </Button>
  );
}