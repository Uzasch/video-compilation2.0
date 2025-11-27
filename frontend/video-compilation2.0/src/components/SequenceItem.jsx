import { useState } from 'react'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { cn } from '@/lib/utils'
import ImageUpload from './ImageUpload'
import { Film, Package, Play, Flag, Trash2, Image, Type, ChevronDown, ChevronRight, Check, X, AlertTriangle, GripVertical, Loader2, RefreshCw, ChevronsUpDown } from 'lucide-react'

const itemConfig = {
  intro: { icon: Play, color: 'bg-green-500/10 text-green-600 border-green-500/30' },
  video: { icon: Film, color: 'bg-blue-500/10 text-blue-600 border-blue-500/30' },
  transition: { icon: Package, color: 'bg-purple-500/10 text-purple-600 border-purple-500/30' },
  outro: { icon: Flag, color: 'bg-red-500/10 text-red-600 border-red-500/30' },
  image: { icon: Image, color: 'bg-pink-500/10 text-pink-600 border-pink-500/30' }
}

export default function SequenceItem({
  item,
  onUpdate,
  onDelete,
  onApplyLogoToAll,
  onVerifyPath,
  isVerifying,
  defaultLogoPath,
  dragHandleProps,
  channels = [],
  onLogoChannelSelect
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [logoPopoverOpen, setLogoPopoverOpen] = useState(false)
  const config = itemConfig[item.item_type]
  const Icon = config.icon

  const canDelete = !['intro', 'outro'].includes(item.item_type)
  const canHaveLogo = item.item_type === 'video'
  const canHaveTextAnimation = item.item_type === 'video'
  const isImage = item.item_type === 'image'
  const canVerifyPath = !isImage && !item.path_available && item.path

  return (
    <Collapsible open={isOpen} onOpenChange={setIsOpen}>
      <div className={`rounded-lg border ${config.color} transition-all`}>
        <CollapsibleTrigger asChild>
          <div className="flex items-center justify-between p-4 cursor-pointer hover:bg-background/50">
            <div className="flex items-center gap-3">
              {/* Drag Handle */}
              {dragHandleProps ? (
                <div
                  {...dragHandleProps}
                  className="cursor-grab active:cursor-grabbing text-muted-foreground hover:text-foreground"
                  onClick={(e) => e.stopPropagation()}
                >
                  <GripVertical className="h-5 w-5" />
                </div>
              ) : (
                <div className="w-5" />
              )}

              <Icon className="h-5 w-5" />
              <div>
                <p className="font-medium text-foreground">
                  {item.title || item.item_type.charAt(0).toUpperCase() + item.item_type.slice(1)}
                </p>
                <p className="text-xs text-muted-foreground">
                  #{item.position}
                  {item.video_id && ` • ${item.video_id}`}
                  {item.duration && ` • ${item.duration.toFixed(1)}s`}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Path status badge */}
              {item.path_available ? (
                <Badge variant="outline" className="bg-green-500/10 text-green-600 border-green-500/30">
                  <Check className="h-3 w-3 mr-1" /> Available
                </Badge>
              ) : item.path ? (
                <Badge variant="outline" className="bg-red-500/10 text-red-600 border-red-500/30">
                  <X className="h-3 w-3 mr-1" /> Not Found
                </Badge>
              ) : (
                <Badge variant="outline" className="bg-amber-500/10 text-amber-600 border-amber-500/30">
                  <AlertTriangle className="h-3 w-3 mr-1" /> No Path
                </Badge>
              )}

              {canDelete && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={(e) => { e.stopPropagation(); onDelete(item.position) }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}

              {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </div>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <div className="px-4 pb-4 pt-2 space-y-4 border-t border-border/50">
            {/* Image upload for image type */}
            {isImage && <ImageUpload item={item} onUpdate={onUpdate} />}

            {/* Manual path input */}
            {!isImage && (
              <div className="space-y-2">
                <Label>Manual Path</Label>
                <div className="flex gap-2">
                  <Input
                    value={item.path || ''}
                    onChange={(e) => onUpdate(item.position, { path: e.target.value, path_available: false })}
                    placeholder="\\SERVER\path\to\video.mp4"
                    className="font-mono text-sm bg-background/50"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    onClick={() => onVerifyPath && onVerifyPath(item.position, item.path)}
                    disabled={!item.path || isVerifying}
                    title="Verify path"
                  >
                    {isVerifying ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                  </Button>
                </div>
                <p className="text-xs text-muted-foreground">
                  Enter path and click verify to check availability
                </p>
              </div>
            )}

            {/* Logo channel selection for videos */}
            {canHaveLogo && (
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Image className="h-4 w-4" /> Logo (Select Channel)
                </Label>
                <div className="flex gap-2">
                  <Popover open={logoPopoverOpen} onOpenChange={setLogoPopoverOpen}>
                    <PopoverTrigger asChild>
                      <Button
                        variant="outline"
                        role="combobox"
                        aria-expanded={logoPopoverOpen}
                        className="flex-1 justify-between bg-background/50 font-normal"
                      >
                        {item.logo_channel || "Select channel for logo..."}
                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                      </Button>
                    </PopoverTrigger>
                    <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                      <Command>
                        <CommandInput placeholder="Search channels..." className="h-9" />
                        <CommandList>
                          <CommandEmpty>No channel found.</CommandEmpty>
                          <CommandGroup>
                            {channels.map((ch) => (
                              <CommandItem
                                key={ch}
                                value={ch}
                                onSelect={() => {
                                  onLogoChannelSelect && onLogoChannelSelect(item.position, ch)
                                  setLogoPopoverOpen(false)
                                }}
                              >
                                {ch}
                                <Check
                                  className={cn(
                                    "ml-auto h-4 w-4",
                                    item.logo_channel === ch ? "opacity-100" : "opacity-0"
                                  )}
                                />
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  <Button variant="outline" size="sm" onClick={() => onUpdate(item.position, { logo_path: defaultLogoPath, logo_channel: null })}>
                    Reset
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => onApplyLogoToAll(item.logo_path)}>
                    Apply All
                  </Button>
                </div>
                {item.logo_path && (
                  <p className="text-xs text-muted-foreground font-mono truncate">
                    {item.logo_path}
                  </p>
                )}
              </div>
            )}

            {/* Text animation for videos */}
            {canHaveTextAnimation && (
              <div className="space-y-2">
                <Label className="flex items-center gap-2">
                  <Type className="h-4 w-4" /> Text Animation
                </Label>
                <Input
                  value={item.text_animation_text || ''}
                  onChange={(e) => onUpdate(item.position, { text_animation_text: e.target.value || null })}
                  placeholder="Text to animate letter-by-letter"
                  className="bg-background/50"
                />
                <p className="text-xs text-muted-foreground">Leave empty to disable</p>
              </div>
            )}
          </div>
        </CollapsibleContent>
      </div>
    </Collapsible>
  )
}
