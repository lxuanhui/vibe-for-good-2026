import type { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'ghost'
}

export function Button({ variant = 'ghost', className = '', ...props }: ButtonProps) {
  const base = 'rounded px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed'
  const variants = {
    primary: 'bg-accent text-bg hover:bg-accent/90',
    ghost: 'border border-border-strong text-text hover:bg-panel-raised',
  }
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />
}
