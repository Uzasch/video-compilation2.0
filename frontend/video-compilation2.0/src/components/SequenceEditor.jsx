import { DragDropContext, Droppable, Draggable } from '@hello-pangea/dnd'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import SequenceItem from './SequenceItem'
import InsertButton from './InsertButton'
import { List } from 'lucide-react'

export default function SequenceEditor({ sequence, onChange, onVerifyPath, isVerifying, channels = [], onLogoChannelSelect }) {
  const updateItem = (position, updates) => {
    const updatedItems = sequence.items.map((item) =>
      item.position === position ? { ...item, ...updates } : item
    )
    onChange({ ...sequence, items: updatedItems })
  }

  const insertItem = (afterPosition, itemType) => {
    const items = [...sequence.items]
    items.forEach(item => {
      if (item.position > afterPosition) item.position++
    })

    const newItem = {
      position: afterPosition + 1,
      item_type: itemType,
      path: null,
      path_available: false,
      logo_path: itemType === 'video' ? sequence.default_logo_path : null,
      text_animation_text: null,
      duration: itemType === 'image' ? 5 : null,
      title: itemType === 'image' ? 'Image Slide' : null
    }

    const insertIndex = items.findIndex(item => item.position === afterPosition)
    items.splice(insertIndex + 1, 0, newItem)
    onChange({ ...sequence, items })
  }

  const deleteItem = (position) => {
    const item = sequence.items.find(i => i.position === position)
    if (item?.item_type === 'intro' || item?.item_type === 'outro') return

    let items = sequence.items.filter(i => i.position !== position)
    items = items.map((item, index) => ({ ...item, position: index + 1 }))
    onChange({ ...sequence, items })
  }

  const handleApplyLogoToAll = (logoPath) => {
    const updatedItems = sequence.items.map((item) =>
      item.item_type === 'video' ? { ...item, logo_path: logoPath } : item
    )
    onChange({ ...sequence, items: updatedItems })
  }

  const handleDragEnd = (result) => {
    if (!result.destination) return

    const sourceIndex = result.source.index
    const destIndex = result.destination.index

    if (sourceIndex === destIndex) return

    // Get the item being moved
    const items = [...sequence.items]
    const movedItem = items[sourceIndex]

    // Don't allow moving intro (must stay first) or outro (must stay last)
    if (movedItem.item_type === 'intro' || movedItem.item_type === 'outro') return

    // Don't allow moving items before intro or after outro
    const introIndex = items.findIndex(i => i.item_type === 'intro')
    const outroIndex = items.findIndex(i => i.item_type === 'outro')

    if (introIndex !== -1 && destIndex <= introIndex) return
    if (outroIndex !== -1 && destIndex >= outroIndex) return

    // Reorder items
    const [removed] = items.splice(sourceIndex, 1)
    items.splice(destIndex, 0, removed)

    // Recalculate positions
    const reorderedItems = items.map((item, index) => ({
      ...item,
      position: index + 1
    }))

    // Recalculate total duration
    const totalDuration = reorderedItems.reduce((sum, item) => sum + (item.duration || 0), 0)

    onChange({ ...sequence, items: reorderedItems, total_duration: totalDuration })
  }

  // Check if item can be dragged
  const canDrag = (item) => {
    return !['intro', 'outro'].includes(item.item_type)
  }

  return (
    <Card className="bg-card/60 backdrop-blur-sm border-border/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <List className="h-5 w-5" />
          Video Sequence
        </CardTitle>
        <CardDescription>
          Drag items to reorder. Review, customize logos and text animations, add transitions.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="sequence">
            {(provided) => (
              <div
                {...provided.droppableProps}
                ref={provided.innerRef}
                className="space-y-2 max-h-[500px] overflow-y-auto pr-4"
              >
                {sequence.items.map((item, index) => (
                  <Draggable
                    key={`item-${item.position}-${index}`}
                    draggableId={`item-${item.position}-${index}`}
                    index={index}
                    isDragDisabled={!canDrag(item)}
                  >
                    {(provided, snapshot) => (
                      <div
                        ref={provided.innerRef}
                        {...provided.draggableProps}
                        style={provided.draggableProps.style}
                        className={snapshot.isDragging ? 'opacity-90 shadow-lg' : ''}
                      >
                        <SequenceItem
                          item={item}
                          onUpdate={updateItem}
                          onDelete={deleteItem}
                          onApplyLogoToAll={handleApplyLogoToAll}
                          onVerifyPath={onVerifyPath}
                          isVerifying={isVerifying}
                          defaultLogoPath={sequence.default_logo_path}
                          dragHandleProps={canDrag(item) ? provided.dragHandleProps : null}
                          channels={channels}
                          onLogoChannelSelect={onLogoChannelSelect}
                        />
                        {item.item_type !== 'outro' && (
                          <InsertButton afterPosition={item.position} onInsert={insertItem} />
                        )}
                      </div>
                    )}
                  </Draggable>
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>
      </CardContent>
    </Card>
  )
}
