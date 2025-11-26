import Layout from '../components/Layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function NewCompilation() {
  return (
    <Layout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">New Compilation</h2>

        <Card>
          <CardHeader>
            <CardTitle>Create New Compilation</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">
              New compilation form will be implemented in Task 7.
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  )
}
