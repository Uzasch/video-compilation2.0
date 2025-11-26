import Layout from '../components/Layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function History() {
  return (
    <Layout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">History</h2>

        <Card>
          <CardHeader>
            <CardTitle>Compilation History</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">
              History list will be implemented in Task 7.
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  )
}
