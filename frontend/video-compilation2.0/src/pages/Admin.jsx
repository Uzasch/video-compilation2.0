import Layout from '../components/Layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function Admin() {
  return (
    <Layout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Admin Panel</h2>

        <Card>
          <CardHeader>
            <CardTitle>Administration</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">
              Admin panel will be implemented in a future task.
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  )
}
