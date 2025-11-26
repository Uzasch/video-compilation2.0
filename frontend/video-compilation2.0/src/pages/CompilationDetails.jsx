import { useParams } from 'react-router-dom'
import Layout from '../components/Layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

export default function CompilationDetails() {
  const { jobId } = useParams()

  return (
    <Layout>
      <div className="space-y-6">
        <h2 className="text-2xl font-bold text-gray-900">Compilation Details</h2>

        <Card>
          <CardHeader>
            <CardTitle>Job: {jobId}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-gray-600">
              Compilation details will be implemented in Task 7.
            </p>
          </CardContent>
        </Card>
      </div>
    </Layout>
  )
}
