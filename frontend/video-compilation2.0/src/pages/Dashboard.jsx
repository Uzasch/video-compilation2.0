import Layout from '../components/Layout'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Link } from 'react-router-dom'
import { FileVideo, History, Activity, Clock, Plus } from 'lucide-react'

export default function Dashboard() {
  const stats = [
    {
      title: 'Total Compilations',
      value: '128',
      description: '+12% from last month',
      icon: FileVideo,
      color: 'text-chart-1',
      bg: 'bg-chart-1/10',
    },
    {
      title: 'Processing Time',
      value: '14m',
      description: 'Average per compilation',
      icon: Clock,
      color: 'text-chart-2',
      bg: 'bg-chart-2/10',
    },
    {
      title: 'Active Jobs',
      value: '3',
      description: 'Currently processing',
      icon: Activity,
      color: 'text-chart-3',
      bg: 'bg-chart-3/10',
    },
  ]

  return (
    <Layout>
      <div className="space-y-8">
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-foreground">Dashboard</h2>
            <p className="text-muted-foreground mt-1">
              Overview of your video compilations and system status.
            </p>
          </div>
          <Link to="/new">
            <Button className="shadow-lg hover:shadow-xl transition-all duration-300">
              <Plus className="mr-2 h-4 w-4" /> New Compilation
            </Button>
          </Link>
        </div>

        {/* Stats Grid */}
        <div className="grid gap-4 md:grid-cols-3">
          {stats.map((stat, index) => (
            <Card key={index} className="bg-card/60 backdrop-blur-sm border-border/50 shadow-sm hover:shadow-md transition-all duration-300 border-none">
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  {stat.title}
                </CardTitle>
                <div className={`p-2 rounded-full ${stat.bg}`}>
                  <stat.icon className={`h-4 w-4 ${stat.color}`} />
                </div>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold text-foreground">{stat.value}</div>
                <p className="text-xs text-muted-foreground mt-1">
                  {stat.description}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Recent Activity Section */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
          <Card className="col-span-4 bg-card/60 backdrop-blur-sm border-border/50 shadow-sm hover:shadow-md transition-all duration-300 border-none">
            <CardHeader>
              <CardTitle className="text-foreground">Recent Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="flex items-center justify-between p-4 rounded-lg bg-background/50 border border-border/50 hover:bg-background/80 transition-colors">
                    <div className="flex items-center gap-4">
                      <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                        <FileVideo className="h-5 w-5 text-primary" />
                      </div>
                      <div>
                        <p className="text-sm font-medium leading-none text-foreground">Compilation #{1000 + i}</p>
                        <p className="text-xs text-muted-foreground mt-1">Processed successfully</p>
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">2h ago</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card className="col-span-3 bg-card/60 backdrop-blur-sm border-border/50 shadow-sm hover:shadow-md transition-all duration-300 border-none">
            <CardHeader>
              <CardTitle className="text-foreground">Quick Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <Link to="/new" className="block">
                <div className="group flex items-center gap-4 p-4 rounded-lg border border-dashed border-border hover:border-primary/50 hover:bg-primary/5 transition-all cursor-pointer">
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <Plus className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-medium text-foreground">Create New</h3>
                    <p className="text-xs text-muted-foreground">Start a new video compilation job</p>
                  </div>
                </div>
              </Link>

              <Link to="/history" className="block">
                <div className="group flex items-center gap-4 p-4 rounded-lg border border-dashed border-border hover:border-primary/50 hover:bg-primary/5 transition-all cursor-pointer">
                  <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                    <History className="h-5 w-5 text-primary" />
                  </div>
                  <div>
                    <h3 className="font-medium text-foreground">View History</h3>
                    <p className="text-xs text-muted-foreground">Check past compilations</p>
                  </div>
                </div>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  )
}
