import * as React from "react"
import { cn } from "cn"
import { Tooltip as TooltipPrimitive } from "radix-ui"

function TooltipProvider({ delayDuration = 180, ...props }) {
  return <TooltipPrimitive.Provider delayDuration={delayDuration} {...props} />
}

function Tooltip(props) {
  return <TooltipPrimitive.Root {...props} />
}

function TooltipTrigger(props) {
  return <TooltipPrimitive.Trigger {...props} />
}

function TooltipContent({ className, sideOffset = 7, children, ...props }) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-md bg-slate-950 px-3 py-2 text-xs leading-relaxed text-white shadow-lg",
          className
        )}
        {...props}
      >
        {children}
        <TooltipPrimitive.Arrow className="fill-slate-950" />
      </TooltipPrimitive.Content>
    </TooltipPrimitive.Portal>
  )
}

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger }
