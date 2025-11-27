import { Button } from '@/components/ui/button'
import { Plus, Film, Package, Image } from 'lucide-react'

export default function InsertButton({ afterPosition, onInsert }) {
  return (
    <div className="flex items-center justify-center py-2 gap-2 opacity-50 hover:opacity-100 transition-opacity">
      <div className="h-[1px] flex-1 bg-border" />
      <div className="flex gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'video')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Film className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'transition')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Package className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => onInsert(afterPosition, 'image')}
        >
          <Plus className="h-3 w-3 mr-1" />
          <Image className="h-3 w-3" />
        </Button>
      </div>
      <div className="h-[1px] flex-1 bg-border" />
    </div>
  )
}
